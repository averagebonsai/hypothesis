# MVP: Economic Simulator (.ipynb)

The focus of this document is to outline an MVP. 

## Direction 
The overall approach is to first define a few parent assets, resuable templates/wrappers that we can then base each economic experiment in. Then, for each specific experiment, we define those assets. Finally, we specific some required experiment-specific parameters, and we run the experiment loop. We repeat this across a few different baseline economic experiments, such as Bertrand competition, Stackelberg competition, and more. 

## Experiment Flow 
1. User provides all required details about economic experiment (especially the type of economic experiment)
2. Muse Spark 1.2 formats the specific configuration for the specific experiment, alongside any additional details provided by the user. Experiment-specific details are shared across all agents. 
3. Each economic agent in the experiment is powered by a single Muse Spark 1.2 agent. There must be no cross-contamination of memory or state across different economic agents -- for example, one agent must not be able to view what another agent's profit is. The agent's choices, profits, and decision traces are stored. 
4. A Muse Spark 1.2 agent generates a log of each agent's decision trace at each point in time (one entry should compare the thoughts of different agents at that point in time), as well as the visualisations required (total profit, price, etc.)

## Technical Implementation
The parent assets to be defined are as follows; 
1. MarketExperiment interface (abstract base class): Structure of an economic experiment, with pre-defined functions like reset, is_done, etc, similar to a RL loop. Action and state for each agent should also be clearly defined. 
2. LLMPrompt (abstract base class): Structure of an LLM's system prompt. 
3. LLMPolicy (abstract base class - parent class / interface): Defines a template for an LLM response, with 2 key components: Action selection, and accompanying justification. 
4. Logging and Visualisation classes/functions. By default, logging should contain a log of each agent's decision trace at each point in time, and visualisations would log (1) Firm profit over time (line graph); (2) Firm price over time (line graph); (3) Market Share over Time (with outside option)
5. A Pydantic class for the LLM, at the end of the experiment, to define the assumptions made during this experiment that would be important for the user to know. 
6. Main execution Loop

Each experiment would then need to define: 
1. Config for each experiment (parameters): Takes the user's specifications for the experiment, and formats specific experiment parameters (e.g number of firms, number of turns, etc.) into a Pydantic class. 
2. SpecificExperiment(MarketExperiment): Defines in detail how the experiment is run (e.g what a step looks like, reset, is_done, etc.)
3. SpecificAgentPrompt(LLMPrompt): The specific prompt behind each economic agent. Takes user input and structures it via a Pydantic class. If no such prompt is given, it returns to a fallback prompt. 
4. SpecificAgentPolicy(LLMPolicy): The specific policy behind each LLM, specifically its outputs. Alongside its chosen action, it should also include a structured decision trace, across a few different fields like "rationale summary" and "confidence score". 

Agent loops would be run in an OpenAI RL Gymnasium Environment, specifically PettingZoo (suited for multi-agent simulations). 

## Structure of .ipynb 
(1) Parent asset implementation (1 cell)
(2) Textbook Bertrand Competition implementation (1 cell) 
(3) Execution of Bertrand Competition implementation, with specified user inputs (1 cell) 
(4) Modified Bertrand Competition implementation and execution (1 cell)
(5) Textbook Stackelberg Competition implementation (1 cell)
(6) Execution of Stackelberg Competition implementation, with specified user inputs (1 cell)

## Specific Experiment Implementation 

### (Textbook) Bertrand Competition 
This experiment should implement textbook Bertrand competition. 

Overall market demand goes down as price goes up, and demand goes entirely to the lower-priced agent (and split equally if they share the same price). This creates a piecewise function that is dependent on whether the price set by p1 or p2 is higher or lower. The overall market demand function is Q = a - b(p1) if p1 < p2, (a - b(p1)) / 2 if p1 = p2, and zero if p1 > p2. 

It should take in user inputs: 
- Marginal Cost
- Fixed Cost
- a (Total Market Demand)
- b (gradient)

### Differentiated Bertrand Competition 
This experiment should implement differentiated Bertrand Competition using the same parent assets, but with different experiment-specific configurations and experiment loops. 

In this case, instead of the piecewise demand function, where overall market demand goes down as price goes up, and demand goes entirely to the lower-priced agent (and split equally if they share the same price); demand for each agent is written as a linear function of both agent's prices. It is negatively correlated with its own prices, and positively correlated with its competitor's prices. An example for agent 1 would be Q_1(p1, p2) = 25 - 4p1 + 2p2. 

For this experiment, it should take in an additional open-ended field where the user can describe how the 2 firms are different from each other. The LLM should, after analysing this, output the 4 partial derivatives (dQ1/p1, dQ2/p1, dQ1/p2, dQ2/p2) that allow for the construction of the demand function. If the user provides these partial derivatives, it should just use this. 

### Differentiated Bertrand Competition (with user-defined modifications)
This experiment should implement differentiated Bertrand competition, again using the same parent assets, and this time with the same experiment loops. However, the configuration for the experiment changes. I want to make demand non-homogenous. 

The user will specify n groups of customers, each with a different number of people, and their own profile. Assume that these customers are homogenous within their own group. 

A logit model is implemented instead. Every group will have descriptions for each agent (making for n x m descriptions). Using this, the LLM (MuseSpark 1.2) will assign a base utility v to each agent corresponding to each customer group, as well as an elasticity parameter alpha. The utility of agent i in the eyes of customer group k is given by u_ik = v_ik - alpha_ik * (p_i), where p_i is the price that the agent set. We also define the utility of the outside option to be equal to 1 (normalising constant). 

We then take a softmax over that u to determine the probability of someone from that customer group purchasing from that firm. We then multiply that by the number of people in each group to determine total demand from each group, and subsequently sum across all groups to generate total demand for a particular firm/agent. 









implements Bertrand competition with 2 key modifications. 

The first modification is that the agents are no longer identical -- or more specifically, the products they offer are no longer identical. The user will supply information on how these 2 agents differ (e.g branding, ESG track record, etc.). The second modification is that demand is no longer homogenous. The user specifies a fixed number of customer groups, n, each with different customer profiles and preferences.



we swap to a logit model, where every customer group's perception of the two firms is taken into consideration. we score their base utility, v, alongside a elasticity parameter alpha, and we take u = v - alpha(price). We then take a softmax over that u to determine the 





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