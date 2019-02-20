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

from System import *
from QuantConnect import *
from QuantConnect.Orders import *
from QuantConnect.Algorithm import QCAlgorithm
from QuantConnect.Algorithm.Framework import QCAlgorithmFramework

from datetime import timedelta, datetime
from decimal import Decimal

#
# Leveraged ETFs (LETF) promise a fixed leverage ratio with respect to an underlying asset or an index.
# A Triple-Leveraged ETF allows speculators to amplify their exposure to the daily returns of an underlying index by a factor of 3. 
#
# Increased volatility generally decreases the value of a LETF over an extended period of time as daily compounding is amplified.
#
# This alpha emits short-biased insight to capitalize on volatility decay for each listed pair of TL-ETFs, by rebalancing the
# ETFs with equal weights each day.
#
# <br><br>This alpha is part of the Benchmark Alpha Series created by QuantConnect which are open sourced so the community and 
# client funds can see an example of an alpha. You can read the source code for this alpha on Github in 
# <a href="https://github.com/QuantConnect/Lean/blob/master/Algorithm.CSharp/Alphas/TripleLeverageETFPairVolatilityDecayAlpha.cs">C#</a>
# or <a href="https://github.com/QuantConnect/Lean/blob/master/Algorithm.Python/Alphas/TripleLeverageETFPairVolatilityDecayAlpha.py">Python</a>.
#
#

class TripleLeveragedETFPairVolatilityDecayAlphaAlgorithm(QCAlgorithmFramework):

    def Initialize(self):

        self.SetStartDate(2018, 1, 1)
        self.SetCash(100000)
        
        # Set zero transaction fees
        self.SetSecurityInitializer(lambda security: security.SetFeeModel(ConstantFeeModel(0)))
        
        # 3X ETF pair tickers
        ultraLong =  ["UGLD","LABU","SOXL"]
        ultraShort = ["DGLD","LABD","SOXS"]

        groups = []
        for i in range(len(ultraLong)):
            group = ETFGroup(self.AddEquity(ultraLong[i], Resolution.Daily).Symbol,
                              self.AddEquity(ultraShort[i], Resolution.Daily).Symbol)
            groups.append(group)

        # Manually curated universe
        self.SetUniverseSelection(ManualUniverseSelectionModel())
        # Select the demonstration alpha model
        self.SetAlpha(RebalancingTripleLeveragedETFAlphaModel(groups))
        # Select our default model types
        self.SetPortfolioConstruction(EqualWeightingPortfolioConstructionModel())
        self.SetExecution(ImmediateExecutionModel())
        self.SetRiskManagement(NullRiskManagementModel())


class RebalancingTripleLeveragedETFAlphaModel(AlphaModel):
    '''
        Rebalance a pair of 3x leveraged ETFs and predict that the value of both ETFs in each pair will decrease.
    '''
    
    def __init__(self, ETFgroups):

        self.ETFgroups = ETFgroups
        self.date = datetime.min.date
        self.Name = "RebalancingTripleLeveragedETFAlphaModel"

    def Update(self, algorithm, data):
        '''Emit an insight each day.'''

        insights = []
        magnitude = 0.0

        # giving an insight period 1 days.
        period = timedelta(days=1)

        for group in self.ETFgroups:
                insights.append(Insight.Price(group.ultraLong, period, InsightDirection.Down, magnitude))
                insights.append(Insight.Price(group.ultraShort, period, InsightDirection.Down, magnitude))

        return insights

class ETFGroup:
    '''
    Group the pair of bull triple leveraged ETFs and bear triple leveraged ETFs
    Args:
        ultraLong: The long-leveraged version of underlying ETF
        ultraShort: The short-leveraged version of the underlying ETF
    '''
    def __init__(self, ultraLong, ultraShort):
        self.ultraLong = ultraLong
        self.ultraShort = ultraShort
