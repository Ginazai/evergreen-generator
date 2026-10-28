def register() -> None:
    from evergreen import registry
    from evergreen.assembly.adapter import AssemblyAdapter

    registry.ADAPTERS["assembly"] = AssemblyAdapter()
