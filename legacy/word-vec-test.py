import gensim.downloader as api

available_models = api.info()['models']

print("Available pre-trained Word2Vec models in Gensim:\n")
for model_name, details in available_models.items():
    if 'word2vec' in model_name.lower():  # find models with 'word2vec' in their name
        print(f"Model: {model_name}")
        print(f"  - Description: {details.get('description')}")


# 1. Load the Google News model (Note: This is ~1.6GB and will take time!)
print("Loading model...")
w2v_google_news = api.load('word2vec-google-news-300')

# 2. Now you can use it
print("Finding similar words:")
print(w2v_google_news.most_similar("beautiful"))

print(w2v_google_news.most_similar_cosmul(positive=['paris', 'USA'], negative=['France']))