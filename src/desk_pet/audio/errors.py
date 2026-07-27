class AudioError(RuntimeError):
    """A user-facing audio operation failed."""


class AudioCancelled(AudioError):
    """The user cancelled recording or playback."""
