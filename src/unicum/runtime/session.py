"""Ownership registry for one load of the mod.

Hot reload is only safe if a load can be undone completely. A hook left in
place, a callback still pending or an event still subscribed survives the
reload and then runs the previous load's code against the new load's state,
which fails in ways that look like the reload itself is broken.

So nothing takes ownership of anything directly: it goes through a Session,
and close() gives all of it back.
"""
import logging

import BigWorld

_logger = logging.getLogger('unicum.runtime')

# Distinguishes "the attribute was inherited" from "it was None".
_ABSENT = object()


class Session(object):
    """Everything a single start() owns, and how to release it."""

    def __init__(self, generation):
        self.generation = generation
        self.alive = True
        self._patches = []
        self._callbacks = set()
        self._subscriptions = []
        self._closers = []

    def on_close(self, func):
        """Register arbitrary teardown, for resources this class cannot model.

        Textures registered with the engine are the motivating case: they
        live outside Python, so nothing collects them when the session goes
        and they would accumulate across reloads.
        """
        self._closers.append(func)
        return func

    def patch(self, holder, name, build):
        """Replace holder.name with build(original), remembering both.

        build() receives the callable being replaced so a hook can delegate
        to it. Keeping the original here rather than in the caller is what
        makes the patch reversible without the caller's cooperation.

        Note that patching a module attribute only reaches callers that look
        the name up at call time. A module doing `from x import f` holds its
        own binding and needs its own patch.
        """
        original = getattr(holder, name)
        replacement = build(original)

        # What gets restored is the attribute as it was *stored*, not what
        # getattr handed back. Two cases differ:
        #
        #   classmethod/staticmethod -- getattr returns something already
        #     bound, and putting that back would change how later calls are
        #     made.
        #   inherited -- the name lives on a base class. setattr would leave
        #     an override behind that was never there, permanently shadowing
        #     the real one, so the undo is a delete.
        # Reading the owner's own __dict__ covers modules, classes and
        # instances alike, and _ABSENT then means precisely "inherited".
        own = getattr(holder, '__dict__', None)
        stored = own.get(name, _ABSENT) if own is not None else original

        setattr(holder, name, replacement)
        self._patches.append((holder, name, stored, replacement))
        return replacement

    def callback(self, delay, func):
        """BigWorld.callback that cannot outlive the session.

        A pending callback keeps the code that scheduled it alive, so without
        the `alive` gate a reload during the delay would run the previous
        load's handler after its state was already torn down.
        """
        box = {}

        def guarded():
            self._callbacks.discard(box.get('id'))
            if not self.alive:
                return
            func()

        box['id'] = BigWorld.callback(delay, guarded)
        self._callbacks.add(box['id'])
        return box['id']

    def repeat(self, interval, func):
        """Run func every `interval` seconds until the session closes.

        Rescheduled after each run rather than on a fixed clock, so a slow
        callback cannot stack up behind itself.
        """

        def tick():
            try:
                func()
            finally:
                if self.alive:
                    self.callback(interval, tick)

        self.callback(interval, tick)

    def fetch(self, url, callback, headers=None, timeout=10.0):
        """BigWorld.fetchURL whose response cannot reach a dead session.

        There is no way to cancel a request in flight, so the gate is the
        only protection: a reload while a roster lookup is on the wire would
        otherwise deliver the answer to the load that asked for it, long
        after its hooks came off.

        The callback runs on the game thread and receives the client's
        response object (`.responseCode`, `.body`, `.headers()`).
        """

        def guarded(response):
            if not self.alive:
                return
            try:
                callback(response)
            except Exception:
                _logger.exception('fetch callback failed for %s', url)

        BigWorld.fetchURL(url, guarded, headers, timeout, 'GET', None)

    def subscribe(self, event, handler):
        """Attach to a WG Event, remembering the exact handler object.

        Detaching needs the same object that was attached, so the handler is
        stored rather than rebuilt at teardown: a fresh bound method or
        lambda would compare unequal and silently fail to detach.
        """
        event += handler
        self._subscriptions.append((event, handler))
        return handler

    def close(self):
        """Release everything, in the reverse order it was taken.

        Marking the session dead comes first so that anything already in
        flight turns into a no-op while the rest is being unwound.
        """
        if not self.alive:
            return
        self.alive = False
        self._cancel_callbacks()
        self._unsubscribe()
        self._run_closers()
        self._restore_patches()

    def _run_closers(self):
        for func in reversed(self._closers):
            try:
                func()
            except Exception:
                _logger.exception('teardown hook failed: %r', func)
        del self._closers[:]

    def _cancel_callbacks(self):
        for handle in self._callbacks:
            try:
                BigWorld.cancelCallback(handle)
            except Exception:
                _logger.exception('failed to cancel callback %r', handle)
        self._callbacks.clear()

    def _unsubscribe(self):
        for event, handler in reversed(self._subscriptions):
            try:
                event -= handler
            except Exception:
                _logger.exception('failed to unsubscribe %r', handler)
        del self._subscriptions[:]

    def _restore_patches(self):
        for holder, name, original, replacement in reversed(self._patches):
            # Compared against the stored attribute, not getattr's result.
            # getattr builds a fresh bound object every call for a
            # classmethod, so an identity test against it never matches --
            # which read as "someone patched over us" and quietly skipped the
            # restore, leaving the hook in place across every reload.
            own = getattr(holder, '__dict__', None)
            current = own.get(name, _ABSENT) if own is not None else getattr(
                holder, name, _ABSENT)
            if current is not replacement:
                # Something replaced our hook and is still live. Restoring
                # the original would delete it without its owner knowing, so
                # the chain is left alone.
                #
                # This is not a cosmetic warning. Every skipped restore
                # leaves a layer behind, and layers accumulate one per
                # reload until calling through them fails -- the modules
                # they close over are long purged, so their globals read as
                # None. Once it appears, only a client restart clears it.
                _logger.error(
                    'LEAK: %s.%s was not restored, something replaced it. '
                    'Hooks will stack until the client is restarted.',
                    getattr(holder, '__name__', holder), name)
                continue
            if original is _ABSENT:
                delattr(holder, name)
            else:
                setattr(holder, name, original)
        del self._patches[:]
