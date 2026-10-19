from pathlib import Path

from deepeval.synthesizer import Synthesizer
from deepeval.synthesizer.config import EvolutionConfig
from deepeval.synthesizer.types import Evolution
from dotenv import load_dotenv
from evals.eval_utils import load_context

load_dotenv()

GOLDENS_DIR = Path(__file__).parent / "goldens"


def generate_goldens() -> None:
    contexts = load_context()
    print(f"Loaded {len(contexts)} contexts")

    # Each context is a single chunk, so MULTICONTEXT / COMPARATIVE (which need
    # several chunks to compare) are left out.
    evolution_config = EvolutionConfig(
        num_evolutions=2,
        evolutions={
            Evolution.REASONING: 0.25,
            Evolution.CONCRETIZING: 0.25,
            Evolution.CONSTRAINED: 0.25,
            Evolution.IN_BREADTH: 0.25,
        },
    )

    synthesizer = Synthesizer(model="gpt-4o-mini", evolution_config=evolution_config)
    goldens = synthesizer.generate_goldens_from_contexts(contexts=contexts, max_goldens_per_context=2)
    print(f"Generated {len(goldens)} goldens")

    synthesizer.save_as(file_type="json", directory=GOLDENS_DIR)


if __name__ == "__main__":
    generate_goldens()
