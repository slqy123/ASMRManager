class DownloadParams:
    def __init__(self, force: bool, replace: bool, filter: bool):
        self.force = force
        self.replace = replace
        self.filter = filter

    @property
    def params(self):
        return {
            "force": self.force,
            "replace": self.replace,
            "filter": self.filter,
        }

    def __str__(self):
        return str(self.params)
