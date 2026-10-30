# MVP: Economic Simulator (.ipynb)

The focus of this document is to outline an MVP. 

The overall approach is to define a few parent assets, resuable templates/wrappers that we can then base each economic experiment in. 
1. MarketExperiment interface (abstract base class)
2. LLMPolicy (abstract base class - parent class / interface); also implement chain-of-thought reasoning here (structured decision trace, like decision factors, expected profit direction, confidence, rationale summary). 
3. Logging and Visualisation classes/functions
4. Main execution Loop

Each experiment would then need to define: 
1. Config for each experiment (parameters) -- Pydantic
2. SpecificExperiment(MarketExperiment)
3. Prompt templates / role definitions for each agent + Pydantic classes - structuring each firm's response (production quantity / price chosen)





## Inputs
The user will give the following inputs: 
- Type of experiment (text): A description of what kind of experiment this is. By default, textbook Bertrand competition. 
- Price range: [a, b], where a and b are lower and upper bounds respectively. (a --> float, b --> float)
- Fixed Cost (optional, float): Zero unless specified. 
- Marginal Cost (optional, float): Fixed marginal cost. If user does not specify, by default it goes to (4a/5 + b/5).
- Firm heterogeneity (text): Define number of agents, how the agents are different. For a textbook Bertrand Economic Experiment, both firms should behave identically. 
- Customer heterogeneity (text): Defines number of customer groups, how many people are in each group, as well as the profile of each group. For textbook experiment, define 1 group of 100 people with identical preferences (because firms are identical, these individuals' purchasing decisions are only informed by price). 
- Number of turns for the experiment (int)
- Total market size (int): Total number of people in market. 

## Experiment Setup 
This would be hosted in a .ipynb, and would be coded in Python. 

### Phase 1: Firm Logit Choice Model & Customer Group Profiling  
On the firm side, an LLM (Muse Spark 1.2) scores the base utilities of each Bertrand agent (firm), alongside the outside option. For 2 Bertrand Agents, the LLM assigns scores to V_A, V_B and V_0, where V_i is the base utility of agent i. V_0, the outside option, is normalised to 0. 

For a textbook Bertrand competition example, V_A = V_B. 

On the customer group side, the same LLM will evaluate each group, and compute a predefined alpha representing elasticity. This alpha would be a constant. This alpha and the base utilities are related by an equation computing the actual utilities of an agent. U_i = V_i - alpha(p_ij), meaning that the utility for Bertrand agent i is given by its base utility minus the customer group specific alpha times the price that agent i offers at time j. 

The probability that a customer therefore chooses to buy from a Bertrand agent, say Bertrand Agent A, P(A) = softmax(U_A) = e^(U_A) / (e^(U_A) + e^(U_B) + e^(U_0)). 

Each customer group has a fixed number of people. The demand for Bertrand Agent A is therefore Q(A) = P(A) * num, where num is the number of people in the group. Profit can therefore be calculated as profit = Q(A) * (p_A - c). 

At the end of this phase, there should be n+1 V constants(n = number of agents, the plus one is for the outside option) and k alpha constants(k = number of customer groups) defined, alongside nxk equations defining the calculation of U (utility of each option as perceived by each customer group). 

### Phase 2: Bertrand Experiment 
This should be implemented in an OpenAI RL Gymnasium, specifically PettingZoo. 

At each turn, each agent, powered by Muse Spark 1.2, would receive the following as inputs alongside their system prompts: 
- Round (int): Capped between 1 and the number of turns for the experiment.
- Market size (int): Total number of people in market. 
- Action (array/list -> float): The (i-1)th entry in this list shows the price chosen by the agent at round i. (following Python's zero-based indexing)
- Profit (array/list -> float): The (i-1)th entry in this list shows the profit earned by the agent at round i. If this is the first round, then the array is empty. 

Other system-level things to track (that should NOT be fed into agent memory): 
- Overall number of people who made purchases from each agent at each point in time, inclusive of outside option

To prevent context bleeding across agents, each Bertrand Agent would need its own action and profit array. Round and Market Size are experiment-specific parameters, not firm-specific ones. 

Each agent would then choose an action, corresponding to the price of the item at that point in time. From the computations listed above, the demand and thus profit for each agent can be calculated. Each agent's action and profit arrays are updated. 

This repeats until the specified number of turns for the experiment have been met. 

### Phase 3: Visualisation 
With the available information, a visualisation agent (Muse Spark 1.2) would plot the following charts using Python Plotting packages such as Matplotlib or Seaborn: 
(1) Firm Profit Over Time (Line Graph)
(2) Firm Price over Time (Line Graph) -- there should also be a horizontal line to denote cost / marginal cost. Ideally, we should observe that prices should go quite close to P = MC. 
(3) Market Share over Time (Line Graph) -- also including the "Outside Option". Verify that the market share at each point in time sums up exactly to 1. 