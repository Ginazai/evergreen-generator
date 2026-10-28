def register() -> None:
    """Registra los adaptadores de audio en el registro del core."""
    from evergreen import registry
    from evergreen.voice_audio.manual import (
        AudioManualAdapter,
        music_prompt,
        song_prompt,
    )
    from evergreen.voice_audio.voice import VoiceAdapter

    registry.ADAPTERS["voice"] = VoiceAdapter()
    registry.ADAPTERS["song"] = AudioManualAdapter("song", song_prompt)
    registry.ADAPTERS["music"] = AudioManualAdapter("music", music_prompt)
