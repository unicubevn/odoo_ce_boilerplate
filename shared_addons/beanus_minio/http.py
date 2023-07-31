#  Copyright (c) by The Bean Family, 2023.
#
#  License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
#  These code are maintained by The Bean Family.
import logging
import os

import werkzeug
from minio import Minio
from redis.client import Redis

from odoo import http
from odoo.http import request, root
from odoo.tools import config

_logger = logging.Logger(__name__)

SESSION_TIMEOUT = 60 * 60 * 24 * 6  # 6 days in seconds

# Override the from_attachment function to show the s3 files
minio_client = Minio(endpoint=config.get('attachment_minio_host', 'bucket.thebeanfamily.org'),
                     region=config.get('attachment_minio_region', 'mylocation'),
                     access_key=config.get('attachment_minio_access_key', '8Uxk9kuEds8iLEIs'),
                     secret_key=config.get('attachment_minio_secret_key', 'Flu7L8eIFme074Rey8W6zOLfZioxFPNz'),
                     secure=config.get('attachment_minio_secure', True))
# Add minio_client to http.Stream
http.Stream.minio_client = minio_client

if config.get('redis_host'):
    # Add  redis_client to http.Stream
    redis_client = Redis(host=config.get('redis_host'),
                         port=int(config.get('redis_port')),
                         db=int(config.get('redis_filepathindex', 1)),
                         password=config.get('redis_pass', None))
    http.Stream.redis_client = redis_client


@classmethod
def from_attachment(cls, attachment):
    """ Create a :class:`~Stream`: from an ir.attachment record. """
    attachment.ensure_one()

    self = cls(
        mimetype=attachment.mimetype,
        download_name=attachment.name,
        conditional=True,
        etag=attachment.checksum,
    )

    if attachment.store_fname:
        """
            Check if the file path in attachment.store_fname is s3 path
            if right, do as following
                - Split 'attachment.store_fname' to array value
                - Check whether the Minio presigned path exist in redis or not
                - if not, create new Minio presigned path, if yes, use one
                - because default expired time of Minio presigned path is 7 days, the redis cache expired time will be
                  6 days to ensure the path always usable
        """
        _logger.debug("Go with store_fname path")
        if "s3" in attachment.store_fname:
            self.type = 'url'
            file_path = str(attachment.store_fname).replace("s3://", "").split("/")
            _logger.debug(f"file_path = {file_path}")
            redis_cache = cls.redis_client.get(f"{file_path[0]}{file_path[1]}{file_path[2]}") if config.get(
                'redis_host') else None
            if redis_cache or redis_cache is not None:
                _logger.debug(f"Redis cache type {type(redis_cache)}")
                self.url = redis_cache.decode("utf-8")
            else:
                self.url = cls.minio_client.presigned_get_object(f'{file_path[0]}', f'{file_path[1]}/{file_path[2]}',
                                                                 response_headers={"response-content-type": f"{attachment.mimetype},"})
                # self.url = cls.minio_client.presigned_get_object(f'{file_path[0]}', f'{file_path[1]}/{file_path[2]}')
                if config.get('redis_host'):
                    cls.redis_client.setex(name=f"{file_path[0]}{file_path[1]}{file_path[2]}", value=str(self.url),
                                       time=SESSION_TIMEOUT)

            _logger.info(f"self.url : {self.url}")
        # Otherwise use the odoo original http flow
        else:
            self.type = 'path'
            self.path = werkzeug.security.safe_join(
                os.path.abspath(config.filestore(request.db)),
                attachment.store_fname
            )
            stat = os.stat(self.path)
            self.last_modified = stat.st_mtime
            self.size = stat.st_size

    elif attachment.db_datas:
        _logger.debug("Go with db_datas path")
        self.type = 'data'
        self.data = attachment.raw
        self.last_modified = attachment['__last_update']
        self.size = len(self.data)

    elif attachment.url:
        _logger.debug("Go with url path")
        # When the URL targets a file located in an addon, assume it
        # is a path to the resource. It saves an indirection and
        # stream the file right away.
        print(f"attachment.url : {attachment.url}")
        static_path = root.get_static_file(
            attachment.url,
            host=request.httprequest.environ.get('HTTP_HOST', '')
        )
        if static_path:
            self = cls.from_path(static_path)
        else:
            self.type = 'url'
            self.url = attachment.url
            print(f"attachment.url  self.url: {self.url}")

    else:
        _logger.debug("Go with others path")
        self.type = 'data'
        self.data = b''
        self.size = 0

    _logger.info(f"last result : {self.url}")
    return self



# Modified from_attachment method
http.Stream.from_attachment = from_attachment
