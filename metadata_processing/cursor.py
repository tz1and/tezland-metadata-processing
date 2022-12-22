import logging
from tortoise import Model

from metadata_processing.models import MetadataStatus

_logger = logging.getLogger('Cursor')


class Cursor:
    def __init__(self, model_class, order_by='transient_id'):
        self.model_class = model_class
        self.current = None
        self.order_by = order_by

    async def next(self) -> Model:
        if self.current is None:
            next = await self.model_class.filter(
                **{f'{self.order_by}__gte': 0},
                #transient_id__lt=20,
                metadata_status=MetadataStatus.New.value
            ).order_by(self.order_by).first()
        else:
            next = await self.model_class.filter(
                **{f'{self.order_by}__gt': getattr(self.current, self.order_by)},
                #transient_id__lt=20,
                metadata_status=MetadataStatus.New.value
            ).order_by(self.order_by).first()

        if next is not None:
            self.current = next

        return next

    def reset(self):
        _logger.debug(f'resetting cursor for {self.model_class.__name__}')
        self.current = None