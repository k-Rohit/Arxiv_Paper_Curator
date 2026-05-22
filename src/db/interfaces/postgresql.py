import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker
from src.db.interfaces.base import BaseDatabase
from src.schemas.database.config import PostgreSQLSettings

logger = logging.getLogger(__name__)

Base = declarative_base()

class PostgreSQLDatabase(BaseDatabase):
     """PostgreSQL database implementation."""
     
     def __init__(self,config: PostgreSQLSettings):
          self.config = config
          self.engine: Optional[Engine] = None
          self.session_factory: Optional[sessionmaker] = None
     
     
