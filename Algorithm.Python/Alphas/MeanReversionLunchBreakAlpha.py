# QUANTCONNECT.COM - Democratizing Finance, Empowering Individuals.
# Lean Algorithmic Trading Engine v2.0. Copyright 2014 QuantConnect Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
from QuantConnect.Orders.Fees import ConstantFeeModel

#
# Academic research suggests that stock market participants generally place their orders at the market open and close.
# Intraday trading volume is J-Shaped, where the minimum trading volume of the day is during lunch-break. Stocks become 
# more volatile as order flow is reduced and tend to mean-revert during lunch-break.
#
# This alpha aims to capture the mean-reversion effect of stocks during lunch-break by ranking stocks in the QC500 universe
# on their return during the hour before noon and predicting mean-reversion in price during lunch-break.
#
# <br><br>This alpha is part of the Benchmark Alpha Series created by QuantConnect which are open sourced so the community 
# and client funds can see an example of an alpha. You can read the source code for this alpha on Github in 
# <a href="https://github.com/QuantConnect/Lean/blob/master/Algorithm.CSharp/Alphas/MeanReversionLunchBreakAlpha.cs">C#</a>
# or <a href="https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/Alphas/MeanReversionLunchBreakAlpha.py">Python</a>.
#

class MeanReversionLunchBreakAlphaAlgorithm(QCAlgorithmFramework):

    def Initialize(self):

        self.SetStartDate(2019, 1, 1)

        self.SetCash(100000)
        
        # Set zero transaction fees
        self.SetSecurityInitializer(lambda security: security.SetFeeModel(ConstantFeeModel(0)))

        # Use QC500 universe selection model 
        self.UniverseSettings.Resolution = Resolution.Hour
        self.SetUniverseSelection(QC500UniverseSelectionModel())
        
        # Use MeanReversionLunchBreakAlphaModel to establish insights
        self.SetAlpha(MeanReversionLunchBreakAlphaModel())

        # Equally weigh securities in portfolio, based on insights
        self.SetPortfolioConstruction(EqualWeightingPortfolioConstructionModel())
        

class MeanReversionLunchBreakAlphaModel(AlphaModel):
    '''Uses the stock price return of one hour before lunch break to predict mean-reversion of stock price during lunch break and creates direction prediction for insights accordingly.'''

    def __init__(self, *args, **kwargs): 
        self.lookback = kwargs['lookback'] if 'lookback' in kwargs else 1
        self.resolution = kwargs['resolution'] if 'resolution' in kwargs else Resolution.Hour
        self.predictionInterval = Time.Multiply(Extensions.ToTimeSpan(self.resolution), self.lookback)
        self.symbolDataBySymbol = {}

    def Update(self, algorithm, data):
        
        if algorithm.Time.hour != 12:
            return []
        
        symbolsReturn = dict()
        
        for security in algorithm.ActiveSecurities.Values:
            if security.HasData:
                open = security.Open
                
                # Do not consider symbol with zero open and avoid division by zero
                if open != 0:
                    symbolsReturn[security.Symbol] = security.Close / open - 1
        
        for key,value in symbolsReturn.items():
            if value > 0:
                # Emit "down" insight for the securities that increased in value one hour before lunch-break
                return [Insight.Price(key, self.predictionInterval, InsightDirection.Down, 0, None)]
            else:
                # Emit "up" insight for the securities that decreased in value one hour before lunch-break
                return [Insight.Price(key, self.predictionInterval, InsightDirection.Up, 0, None)]

        return []
