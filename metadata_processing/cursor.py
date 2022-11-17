import logging
from tortoise import Model

from metadata_processing.models import MetadataStatus

_logger = logging.getLogger('Cursor')


class Cursor:
    def __init__(self, model_class):
        self.model_class = model_class
        self.current = None

    async def next(self) -> Model:
        if self.current is None:
            next = await self.model_class.filter(
                transient_id__gte=0,
                #transient_id__lt=20,
                metadata_status=MetadataStatus.New.value
            ).order_by('transient_id').first()
        else:
            next = await self.model_class.filter(
                transient_id__gt=self.current.transient_id,
                #transient_id__lt=20,
                metadata_status=MetadataStatus.New.value
            ).order_by('transient_id').first()

        if next is not None:
            self.current = next

        return next

    def reset(self):
        _logger.debug(f'resetting cursor for {self.model_class.__name__}')
        self.current = None