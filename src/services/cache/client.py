import hashlib
import json
import logging
from datetime import timedelta
from typing import Optional

import redis
from src.schemas.api.ask import AskRequest, AskResponse
from src.config import RedisSettings