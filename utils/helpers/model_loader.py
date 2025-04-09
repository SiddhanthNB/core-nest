import nltk
from config.logger import logger
from sentence_transformers import SentenceTransformer

logger.debug("Starting to load models...")

embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
logger.debug("SentenceTransformer model loaded successfully.")

# summarizer_model = pipeline("summarization", model="Falconsai/text_summarization")
# logger.debug("Summarization model loaded successfully.")

nltk.download("vader_lexicon")
from nltk.sentiment.vader import SentimentIntensityAnalyzer
analyzer = SentimentIntensityAnalyzer()

logger.debug("Model loading completed.")

def get_embedding_model():
    return embedding_model

def get_sentiment_analyzer():
    return analyzer
