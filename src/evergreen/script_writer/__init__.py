def register() -> None:
    """Registra el adaptador de la etapa `script` en el registro del core."""
    from evergreen import registry
    from evergreen.script_writer.adapter import ScriptAdapter

    registry.ADAPTERS["script"] = ScriptAdapter()
