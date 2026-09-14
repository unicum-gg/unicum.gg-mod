"""A fake BigWorld: callbacks that run when told to, and real HTTP."""


class FakeBigWorld(object):
    """Scheduler that runs when told to, instead of on a frame clock."""

    def __init__(self):
        self.pending = {}
        self.fetched = []
        self._next = 1

    def callback(self, delay, func):
        handle = self._next
        self._next += 1
        self.pending[handle] = func
        return handle

    def cancelCallback(self, handle):
        self.pending.pop(handle, None)

    def fetchURL(self, url, callback, headers, timeout, method, postData):
        """Real HTTP, delivered the way the client delivers it: deferred.

        Keeping it out-of-band matters, because code that accidentally
        depends on the response having already arrived would pass against a
        synchronous fake and deadlock against the game.
        """
        import urllib2
        self.fetched.append(url)
        try:
            # A plain urlopen announces itself as Python-urllib and gets a
            # 403 from the API's bot protection. The client sends its own
            # user agent and is let through, so borrowing a browser's keeps
            # the test measuring the mod rather than the WAF.
            request = urllib2.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            raw = urllib2.urlopen(request, timeout=timeout)
            response = FakeResponse(raw.getcode(), raw.read())
        except Exception as error:
            response = FakeResponse(getattr(error, 'code', 0), '')
        self.callback(0.0, lambda: callback(response))

    def run_pending(self):
        """Fire everything queued right now, once."""
        due, self.pending = self.pending, {}
        for _, func in sorted(due.items()):
            func()


class FakeResponse(object):
    """The shape BigWorld hands back: a code, a body, and headers()."""

    def __init__(self, code, body):
        self.responseCode = code
        self.body = body

    def headers(self):
        return {}


class FakeEvent(object):
    """Stands in for a WG Event, and remembers who is attached."""

    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        if handler in self.handlers:
            self.handlers.remove(handler)
        return self
