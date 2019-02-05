from clr import AddReference
AddReference("System")
AddReference("QuantConnect.Common")
AddReference("QuantConnect.Algorithm")
AddReference("QuantConnect.Indicators")
AddReference("QuantConnect.Algorithm.Framework")


from System import *
from QuantConnect import *
from QuantConnect.Orders import *
from QuantConnect.Algorithm import QCAlgorithm
from QuantConnect.Python import PythonQuandl
from QuantConnect.Data.UniverseSelection import *
from QuantConnect.Indicators import *
from Selection.FundamentalUniverseSelectionModel import FundamentalUniverseSelectionModel

from itertools import chain
from math import ceil
from datetime import timedelta, datetime
from decimal import Decimal
from collections import deque

### Pick stocks according to Joel Greenblatt's Magic Formula
class MagicFormulaAlpha(QCAlgorithmFramework):
    ''' Alpha Streams: Benchmark Alpha: Pick stocks according to Joel Greenblatt's Magic Formula'''

    def Initialize(self):

        self.SetStartDate(2016, 1, 1)
        self.SetCash(100000)

        # select stocks using MagicFormulaUniverseSelectionModel
        self.SetUniverseSelection(MagicFormulaUniverseSelectionModel())

        # Use MagicFormulaAlphaModel to establish insights
        self.SetAlpha(MagicFormulaAlphaModel())

        # Equally weigh securities in portfolio, based on insights
        self.SetPortfolioConstruction(EqualWeightingPortfolioConstructionModel())
        

class MagicFormulaAlphaModel(AlphaModel):
    '''Uses Rate of Change (ROC) to create magnitude prediction for insights.'''

    def __init__(self, *args, **kwargs): 
        self.lookback = kwargs['lookback'] if 'lookback' in kwargs else 1
        self.resolution = kwargs['resolution'] if 'resolution' in kwargs else Resolution.Daily
        self.predictionInterval = Time.Multiply(Extensions.ToTimeSpan(self.resolution), self.lookback)
        self.symbolDataBySymbol = {}
        
    def Update(self, algorithm, data):
        insights = []
        for symbol, symbolData in self.symbolDataBySymbol.items():
            if symbolData.CanEmit: 
                insights.append(Insight.Price(symbol, self.predictionInterval, InsightDirection.Up, symbolData.Return, None))
        return insights

    def OnSecuritiesChanged(self, algorithm, changes):
        
        # clean up data for removed securities
        for removed in changes.RemovedSecurities:
            symbolData = self.symbolDataBySymbol.pop(removed.Symbol, None)
            if symbolData is not None:
                symbolData.RemoveConsolidators(algorithm)

        # initialize data for added securities
        symbols = [ x.Symbol for x in changes.AddedSecurities ]
        history = algorithm.History(symbols, self.lookback, self.resolution)
        if history.empty: return

        tickers = history.index.levels[0]
        for ticker in tickers:
            symbol = SymbolCache.GetSymbol(ticker)

            if symbol not in self.symbolDataBySymbol:
                symbolData = SymbolData(symbol, self.lookback)
                self.symbolDataBySymbol[symbol] = symbolData
                symbolData.RegisterIndicators(algorithm, self.resolution)
                symbolData.WarmUpIndicators(history.loc[ticker])


class SymbolData:
    '''Contains data specific to a symbol required by this model'''
    def __init__(self, symbol, lookback):
        self.Symbol = symbol
        self.ROC = RateOfChange('{}.ROC({})'.format(symbol, lookback), lookback)
        self.Consolidator = None
        self.previous = 0

    def RegisterIndicators(self, algorithm, resolution):
        self.Consolidator = algorithm.ResolveConsolidator(self.Symbol, resolution)
        algorithm.RegisterIndicator(self.Symbol, self.ROC, self.Consolidator)

    def RemoveConsolidators(self, algorithm):
        if self.Consolidator is not None:
            algorithm.SubscriptionManager.RemoveConsolidator(self.Symbol, self.Consolidator)

    def WarmUpIndicators(self, history):
        for tuple in history.itertuples():
            self.ROC.Update(tuple.Index, tuple.close)

    @property
    def Return(self):
        return float(self.ROC.Current.Value)

    @property
    def CanEmit(self):
        if self.previous == self.ROC.Samples:
            return False

        self.previous = self.ROC.Samples
        return self.ROC.IsReady

    def __str__(self, **kwargs):
        return '{}: {:.2%}'.format(self.ROC.Name, (1 + self.Return)**252 - 1)
        

class MagicFormulaUniverseSelectionModel(FundamentalUniverseSelectionModel):
    '''Defines a universe according to Joel Greenblatt's Magic Formula, as a universe selection model for the framework algorithm. 
       From the universe QC500, stocks are ranked using the valuation ratios, Enterprise Value to EBITDA (EV/EBITDA) and Return on Invested Capital (ROIC).
    '''

    def __init__(self,
                 filterFineData = True,
                 universeSettings = None, 
                 securityInitializer = None):
        '''Initializes a new default instance of the MagicFormulaUniverseSelectionModel'''
        super().__init__(filterFineData, universeSettings, securityInitializer)
        
        # Number of stocks in Coarse Universe
        self.NumberOfSymbolsCoarse = 500
        # Number of sorted stocks in the fine selection subset using the valuation ratio, EV to EBITDA (EV/EBITDA)
        self.NumberOfSymbolsFine = 20
        # Final number of stocks in security list, after sorted by the valuation ratio, Return on Assets (ROA)
        self.NumberOfSymbolsInPortfolio = 10
        
        self.lastMonth = -1
        self.dollarVolumeBySymbol = {}
        self.symbols = []

    def SelectCoarse(self, algorithm, coarse):
        '''Performs coarse selection for constituents.
        The stocks must have fundamental data
        The stock must have positive previous-day close price
        The stock must have positive volume on the previous trading day'''
        coarse = list(coarse)

        if len(coarse) == 0:
            return self.symbols

        month = coarse[0].EndTime.month
        if month == self.lastMonth:
            return self.symbols

        self.lastMonth = month

        # The stocks must have fundamental data
        # The stock must have positive previous-day close price
        # The stock must have positive volume on the previous trading day
        filtered = [x for x in coarse if x.HasFundamentalData
                                      and x.Volume > 0
                                      and x.Price > 0]
        # sort the stocks by dollar volume and take the top 1000
        top = sorted(filtered, key=lambda x: x.DollarVolume, reverse=True)[:self.NumberOfSymbolsCoarse]

        self.dollarVolumeBySymbol = { i.Symbol: i.DollarVolume for i in top }

        self.symbols = list(self.dollarVolumeBySymbol.keys())

        return self.symbols


    def SelectFine(self, algorithm, fine):
        '''QC500: Performs fine selection for the coarse selection constituents
        The company's headquarter must in the U.S.
        The stock must be traded on either the NYSE or NASDAQ
        At least half a year since its initial public offering
        The stock's market cap must be greater than 500 million
        
        
        Magic Formula: Rank stocks by Enterprise Value to EBITDA (EV/EBITDA)
        Rank subset of previously ranked stocks (EV/EBITDA), using the valuation ratio Return on Invested Capital (ROIC)'''

        # QC500:
        ## The company's headquarter must in the U.S.
        ## The stock must be traded on either the NYSE or NASDAQ
        ## At least half a year since its initial public offering
        ## The stock's market cap must be greater than 500 million
        filteredFine = [x for x in fine if x.CompanyReference.CountryId == "USA"
                                        and (x.CompanyReference.PrimaryExchangeID == "NYS" or x.CompanyReference.PrimaryExchangeID == "NAS")
                                        and (algorithm.Time - x.SecurityReference.IPODate).days > 180
                                        and x.EarningReports.BasicAverageShares.ThreeMonths * x.EarningReports.BasicEPS.TwelveMonths * x.ValuationRatios.PERatio > 5e8]
        count = len(filteredFine)
        if count == 0: return []

        myDict = dict()
        percent = float(self.NumberOfSymbolsFine / count)

        # select stocks with top dollar volume in every single sector
        for key in ["N", "M", "U", "T", "B", "I"]:
            value = [x for x in filteredFine if x.CompanyReference.IndustryTemplateCode == key]
            value = sorted(value, key=lambda x: self.dollarVolumeBySymbol[x.Symbol], reverse = True)
            myDict[key] = value[:ceil(len(value) * percent)]


        # stocks in QC500 universe 
        topFine = list(chain.from_iterable(myDict.values()))[:self.NumberOfSymbolsCoarse]


        #  Magic Formula: 
        ## Rank stocks by Enterprise Value to EBITDA (EV/EBITDA)
        ## Rank subset of previously ranked stocks (EV/EBITDA), using the valuation ratio Return on Invested Capital (ROIC)

        
        # sort stocks in the security universe of QC500 based on Enterprise Value to EBITDA valuation ratio
        sortedByEVToEBITDA = sorted(topFine, key=lambda x: x.ValuationRatios.EVToEBITDA , reverse=True)

        # sort subset of stocks that have been sorted by Enterprise Value to EBITDA, based on the valuation ratio Return on Invested Capital (ROIC)
        sortedByROIC = sorted(sortedByEVToEBITDA[:self.NumberOfSymbolsFine], key=lambda x: x.OperationRatios.ROIC.OneYear, reverse=False)
        
        # retrieve list of securites in portfolio
        top = sortedByROIC[:self.NumberOfSymbolsInPortfolio]
        self.symbols = [f.Symbol for f in top]
        
        return self.symbols
