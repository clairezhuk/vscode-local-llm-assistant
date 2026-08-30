class Router:
    def __init__(self):
        self.m = None
    def add_middleware(self, m):
        self.m = m
    def handle(self, req):
        return self.m.process(req)