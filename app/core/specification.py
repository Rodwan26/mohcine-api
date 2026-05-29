from abc import ABC, abstractmethod

from sqlalchemy import Select


class Specification(ABC):
    def filters(self, query: Select) -> Select:
        return query

    def joins(self, query: Select) -> Select:
        return query

    def options(self, query: Select) -> Select:
        return query

    def ordering(self, query: Select) -> Select:
        return query

    def apply(self, query: Select) -> Select:
        query = self.joins(query)
        query = self.filters(query)
        query = self.options(query)
        query = self.ordering(query)
        return query
