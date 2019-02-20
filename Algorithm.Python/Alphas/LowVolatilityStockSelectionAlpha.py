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

from Selection.QC500UniverseSelectionModel import QC500UniverseSelectionModel
from Selection.FundamentalUniverseSelectionModel import FundamentalUniverseSelectionModel

from itertools import chain
from math import ceil
from datetime import timedelta, datetime
from decimal import Decimal
from collections import deque
import pandas as pd

#
# Portfolios that consist of low-volatility stocks tend to have higher risk-adjusted returns than portfolios that include high-volatility stocks. 
# Low volatility stocks are often considered to be a "safe" investment option by market participants as the earnings of low-volatility stocks tend to be relatively stable.
#
# This alpha picks ten stocks from the QC500 universe that have the lowest volatility based on the standard deviation of daily returns for the last 252 days.
#
# Source: Kakushadze, Zura, and Juan Andrés Serur. “3.4 Stocks.” 151 Trading Strategies, Palgrave Macmillan, 2018, pp. 44–45.
#
# <br><br>This alpha is part of the Benchmark Alpha Series created by QuantConnect which are open sourced so the community and client funds can see an example
# of an alpha. You can read the source code for this alpha on Github in 
# <a href="https://github.com/QuantConnect/Lean/blob/master/Algorithm.CSharp/Alphas/LowVolatilityStockSelectionAlpha.cs">C#</a>
# or <a href="https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/Alphas/LowVolatilityStockSelectionAlpha.py">Python</a>.
#

class LowVolatilityStockSelectionAlphaAlgorithm(QCAlgorithmFramework):

    def Initialize(self):

        self.SetStartDate(2019, 1, 1)

        self.SetCash(100000)
        
        # Set zero transaction fees
        self.SetSecurityInitializer(lambda security: security.SetFeeModel(ConstantFeeModel(0)))
        
        # Use QC500 universe selection model 
        self.UniverseSettings.Resolution = Resolution.Daily
        self.SetUniverseSelection(QC500UniverseSelectionModel())
            
        # Use LowVolatilitySelectionAlphaModel to establish insights
        self.SetAlpha(LowVolatilitySelectionAlphaModel())

        # Equally weigh securities in portfolio, based on insights
        self.SetPortfolioConstruction(EqualWeightingPortfolioConstructionModel())
        

class LowVolatilitySelectionAlphaModel(AlphaModel):
    '''Uses ranking of volatility to create direction prediction for insights'''

    def __init__(self, *args, **kwargs): 
        self.lookback = kwargs['lookback'] if 'lookback' in kwargs else 252
        self.numberOfStocks = kwargs['numberOfStocks'] if 'numberOfStocks' in kwargs else 10
        self.resolution = kwargs['resolution'] if 'resolution' in kwargs else Resolution.Daily
        self.predictionInterval = Time.Multiply(Extensions.ToTimeSpan(self.resolution), 1)

    def Update(self, algorithm, data):
        
        insights = []
        symbols = []
        
        # Retrieve symbols for active securities that have data
        for security in algorithm.ActiveSecurities.Values:
            if security.HasData:
                symbols.append(security.Symbol)

        # Retrieve price history for all securities in the security universe
        hist = algorithm.History(symbols, self.lookback, self.resolution)
        
        # Return 'None' if no history exists
        if hist.empty:
            algorithm.Log(f"No data on {algorithm.Time}")
            return insights
    
        # Get close price for securities 
        hist = hist.close.unstack(level=0)
        
        # Retrieve the standard deviation value of returns for securities
        stdDev=hist.pct_change().std().tolist()
        
        symbolsVol = dict(zip(symbols,stdDev))
        
        number_of_stocks = min(len(symbolsVol), self.numberOfStocks)
        
        # Rank and retrieve the securities that have the lowest volatiltiy
        lowVol = dict(sorted(symbolsVol.items(), key=lambda kv: kv[1],reverse=False)[0:number_of_stocks])
        
        algorithm.Log("Low vol : " + str(lowVol))

        # Emit "up" insight for the securities with the lowest volatility
        for key,value in lowVol.items():
            insights.append(Insight.Price(key, self.predictionInterval, InsightDirection.Up, 0, None))

        return insights
