import time


class SafeChatState:
    """
    Простое хранилище состояния чата с TTL-очисткой.
    Все обращения синхронные (обычные dict-like get/set/pop), TTL спасает от роста.
    """

    def __init__(self, ttl: float = 3600.0, evict_interval: float = 300.0):
        self._states: dict[int, tuple[float, dict]] = {}
        self._ttl = ttl
        self._evict_interval = evict_interval
        self._last_evict = time.time()

    def _evict_expired(self, force: bool = False) -> None:
        now = time.time()
        if not force and (now - self._last_evict) < self._evict_interval:
            return
        self._last_evict = now
        if not self._states:
            return
        expired = [k for k, (ts, _) in self._states.items() if (now - ts) > self._ttl]
        for k in expired:
            self._states.pop(k, None)

    def get(self, chat_id: int, default=None):
        self._evict_expired()
        entry = self._states.get(chat_id)
        return entry[1] if entry else default

    def set(self, chat_id: int, data: dict) -> None:
        self._states[chat_id] = (time.time(), data)

    def pop(self, chat_id: int, default=None):
        entry = self._states.pop(chat_id, None)
        return entry[1] if entry else default

    def __getitem__(self, chat_id: int):
        self._evict_expired()
        return self._states[chat_id][1]

    def __setitem__(self, chat_id: int, data: dict):
        self.set(chat_id, data)

    def __delitem__(self, chat_id: int):
        self._states.pop(chat_id, None)

    def __contains__(self, chat_id: int):
        self._evict_expired()
        return chat_id in self._states

    def __len__(self) -> int:
        self._evict_expired()
        return len(self._states)


chat_states = SafeChatState()
chat_tasks = SafeChatState(ttl=600.0)
