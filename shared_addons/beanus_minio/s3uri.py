#  Copyright (c) by The Bean Family, 2023.
#
#  License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
#  These code are maintained by The Bean Family.

import re


class S3Uri(object):

    _url_re = re.compile("^s3:///*([^/]*)/?(.*)", re.IGNORECASE | re.UNICODE)

    def __init__(self, uri):
        match = self._url_re.match(uri)
        if not match:
            raise ValueError("%s: is not a valid S3 URI" % (uri,))
        self._bucket, self._item = match.groups()

    def bucket(self):
        return self._bucket

    def item(self):
        return self._item