from typing import Any, Generic, TypeVar

from sqlalchemy import select, delete as sa_delete, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model_cls: type[ModelT]):
        self._session = session
        self._model = model_cls

    async def get(self, id: Any) -> ModelT | None:
        return await self._session.get(self._model, id)

    async def find_one(self, **filters) -> ModelT | None:
        stmt = select(self._model).filter_by(**filters).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_all(self, **filters) -> list[ModelT]:
        stmt = select(self._model).filter_by(**filters)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ModelT:
        instance = self._model(**kwargs)
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def update(self, id: Any, **kwargs) -> ModelT | None:
        instance = await self.get(id)
        if not instance:
            return None
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self._session.flush()
        return instance

    async def delete(self, id: Any) -> bool:
        instance = await self.get(id)
        if not instance:
            return False
        await self._session.delete(instance)
        await self._session.flush()
        return True

    async def delete_all(self, **filters) -> int:
        stmt = sa_delete(self._model).filter_by(**filters).returning(self._model.id)
        result = await self._session.execute(stmt)
        return len(result.all())
