from channels.finance.brain import FinanceBrain
from channels.mystery.brain import MysteryBrain

CHANNEL_REGISTRY = {
    "finance": FinanceBrain,
    "mystery": MysteryBrain,
}