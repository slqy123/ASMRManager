class DownloadParams:
    def __init__(
        self, force: bool, replace: bool, check_name: bool, check_tag: bool
    ):
        self.force = force
        self.replace = replace
        self.check_name = check_name
        self.check_tag = check_tag

    @property
    def params(self):
        return {
            "force": self.force,
            "replace": self.replace,
            "check_name": self.check_name,
            "check_tag": self.check_tag,
        }

    def __str__(self):
        return str(self.params)
