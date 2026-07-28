from desk_pet.agent.connectors import CONNECTOR_SPECS, connector_tools_from_environment


def test_no_connector_tokens_means_no_private_tools() -> None:
    assert connector_tools_from_environment({}) == []


def test_each_supported_connector_can_be_enabled_independently() -> None:
    for spec in CONNECTOR_SPECS:
        tools = connector_tools_from_environment(
            {spec.token_environment_variable: f"token-for-{spec.label}"}
        )

        assert len(tools) == 1
        tool = tools[0]
        assert tool["connector_id"] == spec.connector_id
        assert tool["authorization"] == f"token-for-{spec.label}"
        assert tool["allowed_tools"] == list(spec.read_only_tools)
        assert tool["require_approval"] == "never"


def test_connector_tool_lists_are_read_only() -> None:
    forbidden_words = ("send", "create", "update", "delete", "modify", "move")

    for spec in CONNECTOR_SPECS:
        assert spec.read_only_tools
        assert all(
            not any(word in tool_name for word in forbidden_words)
            for tool_name in spec.read_only_tools
        )
