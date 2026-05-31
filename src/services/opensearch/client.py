""" Unified Opensearch client supporting both simple BM25 and hybrid search  """

import logging
from typing import Any, Dict, List, Optional

from opensearchpy import OpenSearch
from src.config import Settings

from .index_config_hybrid import ARXIV_PAPERS_CHUNKS_MAPPING, HYBRID_RRF_PIPELINE
from .query_builder import QueryBuilder

logger = logging.getLogger(__name__)

class OpenSearchClient:
     """OpenSearch client supporting BM25 and hybrid search with native RRF."""
     
     def __init__(
          self,
          host: str,
          settings: Settings
     ):
          self.host = host
          self.settings = settings
          self.index_name = f"{settings.opensearch.index_name}-{settings.opensearch.chunk_index_suffix}"
          
          self.client = OpenSearch(
               host = [host],
               use_ssl = False,
               verify_certs=False,
               ssl_show_warn=False,
          )
          
          logger.info(f"OpenSearch client initialized with host: {host}")
          
     def health_check(self) -> bool:
          """Check if OpenSearch cluster is healthy."""
          try:
               health = self.client.cluster.health()
               return health["status"] in ["green", "yellow"]
          except Exception as e:
               logger.error(f"Health check failed: {e}")
               return False
          
     def get_index_stats(self) -> Dict[str, Any]:
            
          """Get statistics for the hybrid index."""
          try:
               if not self.client.indices.exists(index=self.index_name):
                    return {"index_name": self.index_name, "exists": False, "document_count": 0}

               stats_response = self.client.indices.stats(index=self.index_name)
               index_stats = stats_response["indices"][self.index_name]["total"]

               return {
               "index_name": self.index_name,
               "exists": True,
               "document_count": index_stats["docs"]["count"],
               "deleted_count": index_stats["docs"]["deleted"],
               "size_in_bytes": index_stats["store"]["size_in_bytes"],
          }

          except Exception as e:
               logger.error(f"Error getting index stats: {e}")
               return {"index_name": self.index_name, "exists": False, "document_count": 0, "error": str(e)}
          
     