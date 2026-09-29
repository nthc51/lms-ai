class InMemoryStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def presign_put(self, key, expires_s=900):
        return f"memory://put/{key}"

    async def presign_get(self, key, expires_s=3600, download_name=None):
        return f"memory://get/{key}"

    async def stat_size(self, key):
        data = self.objects.get(key)
        return None if data is None else len(data)

    async def read_head(self, key, n=2048):
        return self.objects[key][:n]

    async def read_all(self, key):
        return self.objects[key]

    async def put(self, key, data, mime):
        self.objects[key] = data

    async def remove(self, key):
        self.objects.pop(key, None)
