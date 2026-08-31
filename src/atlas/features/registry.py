_TOOLS = {}


def register(name):
    """Registers a tool class under the configuration key that enables it."""
    def decorator(tool_class):
        _TOOLS[name] = tool_class
        return tool_class
    return decorator


def registered_names():
    """Every tool name atlas knows how to build."""
    return sorted(_TOOLS)


def build_tools(window, tools_config):
    """
    Builds the tools the configuration switches on.

    A disabled tool is never constructed, so it costs nothing and cannot add
    menu entries or panels. That is what keeps a default launch a plain viewer
    rather than a kitchen sink.

    Returns:
        dict: name -> constructed tool, for the tools that were enabled.
    """
    built = {}
    for name in tools_config.enabled_names():
        tool_class = _TOOLS.get(name)
        if tool_class is None:
            continue
        settings = getattr(tools_config, name)
        tool = tool_class(window, settings)
        tool.build()
        built[name] = tool
    return built


class Tool:
    """Base class for an optional tool."""

    def __init__(self, window, settings):
        self.window = window
        self.settings = settings
        self.view_model = window.view_model

    def build(self):
        """Adds this tool's menu entries and panels to the window."""
        raise NotImplementedError
