from abc import ABC, abstractmethod
from typing import Dict, List, Any


class DBInterface(ABC):

    @abstractmethod
    def create(self, *args, **kwargs):
        pass

    @abstractmethod
    def delete(self, *args, **kwargs):
        pass

    @abstractmethod
    def insert(self, *args, **kwargs):
        pass
    
    @abstractmethod
    def find(self, *args, **kwargs):
        pass

    @abstractmethod
    def find_all(self, *args, **kwargs):
        pass

    @abstractmethod
    async def get_recent(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch last `limit` documents sorted by timestamp.
        """
        ...
