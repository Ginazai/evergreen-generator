def register() -> None:
    """Registra los adaptadores de las etapas visuales en el registro del core."""
    from evergreen import registry
    from evergreen.visuals.adapter import ImageAdapter

    for stage in ("visuals", "characters", "scenes"):
        registry.ADAPTERS[stage] = ImageAdapter()
