"""Bike insights agent template for custom extensions."""

from ingenious.config.settings import IngeniousSettings
from ingenious.models.agent import Agent, Agents, IProjectAgents


class ProjectAgents(IProjectAgents):
    """Bike insights project agent configuration.

    Defines the set of agents used in the bike insights multi-agent workflow,
    including sentiment analysis, fiscal analysis, summarization, and specialized
    bike lookup capabilities.
    """

    def Get_Project_Agents(self, config: IngeniousSettings) -> Agents:
        """Get the project agents configuration for bike insights.

        Args:
            config: The Ingenious settings configuration object.

        Returns:
            An Agents object containing the configured agents for the bike insights project.
        """
        local_agents = []
        local_agents.append(
            Agent(
                agent_name="customer_sentiment_agent",
                agent_model_name="gpt-5-mini",
                agent_display_name="Customer Sentiment",
                agent_description="A sample agent.",
                agent_type="researcher",
                model=None,
                system_prompt=None,
                log_to_prompt_tuner=True,
                return_in_response=False,
            )
        )
        local_agents.append(
            Agent(
                agent_name="fiscal_analysis_agent",
                agent_model_name="gpt-5-mini",
                agent_display_name="Fiscal Analysis",
                agent_description="A sample agent.",
                agent_type="researcher",
                model=None,
                system_prompt=None,
                log_to_prompt_tuner=True,
                return_in_response=False,
            )
        )
        local_agents.append(
            Agent(
                agent_name="summary",
                agent_model_name="gpt-5-mini",
                agent_display_name="Summarizer",
                agent_description="A sample agent.",
                agent_type="summary",
                model=None,
                system_prompt=None,
                log_to_prompt_tuner=True,
                return_in_response=True,
            )
        )
        local_agents.append(
            Agent(
                agent_name="user_proxy",
                agent_model_name="gpt-5-mini",
                agent_display_name="user_proxy_agent",
                agent_description="A sample agent.",
                agent_type="user_proxy",
                model=None,
                system_prompt=None,
                log_to_prompt_tuner=False,
                return_in_response=False,
            )
        )
        local_agents.append(
            Agent(
                agent_name="bike_lookup_agent",
                agent_model_name="gpt-5-mini",
                agent_display_name="bike_lookup_agent",
                agent_description="A sample agent.",
                agent_type="user_proxy",
                model=None,
                system_prompt=None,
                log_to_prompt_tuner=True,
                return_in_response=False,
            )
        )

        return Agents(agents=local_agents, config=config)
