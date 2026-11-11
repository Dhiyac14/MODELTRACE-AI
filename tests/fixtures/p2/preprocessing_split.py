"""DEV FIXTURE (Person 2): stand-in for engine/preprocessing.py. Splits the data used by every model."""
import pandas as pd
from sklearn.model_selection import train_test_split

TARGET = "default.payment.next.month"

df = pd.read_csv("data/processed/credit_default_clean.csv")
train, test = train_test_split(df, test_size=0.2, stratify=df[TARGET], random_state=42)
train.to_csv("data/processed/train.csv", index=False)
test.to_csv("data/processed/test.csv", index=False)
