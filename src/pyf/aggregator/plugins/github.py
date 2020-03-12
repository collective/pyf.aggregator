class load_github_stats:

    def __init__(self, settings):
        self.token = settings.get("github_token")

    def __call__(self, identifier, data):
        return data
