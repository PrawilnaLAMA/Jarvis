# train_classifier.py
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import joblib
import re

class CommandClassifier:
    def __init__(self):
        self.pipeline = None
        self.classes_ = None
    
    def preprocess_text(self, text):
        """Proste czyszczenie tekstu"""
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)  # Usuwanie znaków interpunkcyjnych
        return text
    
    def prepare_data(self, training_data):
        """Przygotowanie danych treningowych"""
        texts = [self.preprocess_text(text) for text, label in training_data]
        labels = [label for text, label in training_data]
        return texts, labels
    
    def train(self, training_data):
        """Trenowanie modelu"""
        print("Przygotowywanie danych...")
        texts, labels = self.prepare_data(training_data)
        
        # Tworzenie pipeline
        self.pipeline = Pipeline([
            ('tfidf', TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=1500,
                min_df=2,
                max_df=0.8,
                stop_words=['się', 'w', 'na', 'i', 'o', 'z', 'a', 'do', 'od', 'czy']  # polskie stop words
            )),
            ('clf', LogisticRegression(
                C=1.0,
                max_iter=1000,
                random_state=42
            ))
        ])
        
        print("Trenowanie modelu...")
        self.pipeline.fit(texts, labels)
        
        # Zapisywanie klas
        self.classes_ = self.pipeline.classes_
        
        # Ewaluacja
        X_train, X_test, y_train, y_test = train_test_split(
            texts, labels, test_size=0.2, random_state=42, stratify=labels
        )
        
        self.pipeline.fit(X_train, y_train)
        y_pred = self.pipeline.predict(X_test)
        
        print(f"Accuracy: {accuracy_score(y_test, y_pred):.4f}")
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred))
        
        return self
    
    def predict(self, text):
        """Predykcja dla nowego tekstu"""
        if self.pipeline is None:
            raise ValueError("Model nie został wytrenowany!")
        
        processed_text = self.preprocess_text(text)
        prediction = self.pipeline.predict([processed_text])
        probability = self.pipeline.predict_proba([processed_text])
        
        return {
            'command': prediction[0],
            'confidence': np.max(probability[0]),
            'all_probabilities': dict(zip(self.pipeline.classes_, probability[0]))
        }
    
    def save_model(self, filepath):
        """Zapisanie modelu"""
        joblib.dump(self, filepath)
        print(f"Model zapisany jako {filepath}")
    
    @classmethod
    def load_model(cls, filepath):
        """Wczytanie modelu"""
        return joblib.load(filepath)