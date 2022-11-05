!pip install transformers

from transformers import AutoTokenizer, AutoModel
import torch
import numpy as np
from torch import nn
from torch import optim
from torch.nn import functional as F
import pandas as pd
import os

class SiameseClassifier(nn.Module):
  def __init__(self):
    super().__init__()
    self.l1 = nn.Linear(768, 384)
    self.l2 = nn.Linear(384, 256)
    self.l3 = nn.Linear(256, 128)

    self.l4 = nn.Linear(2 * 128, 128)
    self.l5 = nn.Linear(128, 64)

  def forward(self, x, y):
    x = F.relu(self.l1(x))
    x = F.relu(self.l2(x))
    x = self.l3(x)

    y = F.relu(self.l1(y))
    y = F.relu(self.l2(y))
    y = self.l3(y)

    out = torch.abs(F.cosine_similarity(x, y).unsqueeze(1))

    return out

class MyModel():
  def __init__(self):
    # do here any initializations you require
    self.classifier = SiameseClassifier()
    # load tokenizer and model
    self.tokenizer = AutoTokenizer.from_pretrained("dumitrescustefan/bert-base-romanian-uncased-v1")
    self.model = AutoModel.from_pretrained("dumitrescustefan/bert-base-romanian-uncased-v1").cuda()

  def create_batch(self, inputs):
    # batching
    el = 0
    BATCH_SIZE_TRAIN = 100
    batch = []
    batch_data = []
    for (sc, ta, tb) in inputs:
        labels = torch.tensor(np.array([[sc / 5.0]]), dtype=torch.float32).to(torch.device("cuda:0"))
        ta = ta.to(torch.device("cuda:0"))
        tb = tb.to(torch.device("cuda:0"))
        inputs = torch.cat((ta, tb), 0).unsqueeze(0)
        batch.append((labels, inputs))
        el+=1

        if el == BATCH_SIZE_TRAIN:
          labels_batch = torch.cat([e[0] for e in batch])
          inputs_batch = torch.cat([e[1] for e in batch]).permute(1,0,2)
          el = 0
          batch = []
          batch_data.append((labels_batch, inputs_batch))
    return batch_data

  def fetch_data(self, df):
    columns = ['text_a', 'text_b']
    return [(e[0], self.mean_polling(self.tokenize_sentence(e[1])), self.mean_polling(self.tokenize_sentence(e[2]))) for e in df.to_numpy()]

  def mean_polling(self, out):
    mp = torch.nn.AvgPool1d(out.shape[-2], stride=out.shape[-2])(out.permute(0,2,1))
    return mp.view(mp.shape[:-1])

  def tokenize_sentence(self, text):
    text = text.replace("ţ", "ț").replace("ş", "ș").replace("Ţ", "Ț").replace("Ş", "Ș") 
    input_ids = torch.tensor(self.tokenizer.encode(text, add_special_tokens=True)).unsqueeze(0).to(torch.device("cuda:0"))  # Batch size 1  
    outputs = self.model(input_ids)
    out = outputs[0].detach().to(torch.device("cpu"))
    del input_ids
    del outputs
    torch.cuda.empty_cache()
    return out # The last hidden-state is the first element of the output tuple
    
  def test_model(self, inputs):
    test_results = []

    with torch.no_grad():
        for (score, text_a, text_b) in inputs:
          outputs = self.classifier(text_a.to(torch.device("cuda:0")), text_b.to(torch.device("cuda:0")))
          test_results.append(outputs.cpu().numpy()[0][0] * 5)

    # add random values - for demo purposes
    pred = pd.Series(test_results)

    # compute correlation score between predictions and groundtruth
    prediction_correlation_score = pd.Series([e[0] for e in inputs]).corr(pred, method='pearson')
    print(prediction_correlation_score)
    return prediction_correlation_score

  def load(self, model_resource_folder):
    self.classifier.load_state_dict(torch.load('{}/model.thw'.format(model_resource_folder)))
    self.classifier.eval()    
    # we'll call this code before prediction
    # use this function to load any pretrained model and any other resource, from the given folder path

  def train(self, train_data_frame, validation_data_frame, model_resource_folder):
    # we'll call this function right after init
    # place here all your training code
    # at the end of training, place all required resources, trained model, etc in the given model_resource_folder
    os.mkdir(model_resource_folder, 0o777)
    # data preprocessed for classification
    train = self.fetch_data(train_data_frame)
    valid = self.fetch_data(validation_data_frame)
    
    self.classifier.cuda()
    
    train_batch = self.create_batch(train)
    
    criterion = nn.BCELoss()
    optimizer = optim.Adadelta(self.classifier.parameters(), lr=0.007)

    bscore = 0
    EPOCHS = 3000
    for epoch in range(EPOCHS):
      running_loss = 0.0
      for i, data in enumerate(train_batch):
        labels, inputs = data
        ia = inputs[0]
        ib = inputs[1]

        optimizer.zero_grad()


        outputs = self.classifier(ia, ib)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        # print statistics
        running_loss += loss.item()
      
      if epoch % 10 == 0:
        print('epoch:', epoch)
        score = self.test_model(valid)
        if bscore < score:
          bscore = score
          torch.save(self.classifier.state_dict(),'{}/model.thw'.format(model_resource_folder))

  def predict(self, test_data_frame):
    # we'll call this function after the load()
    # use this place to run the prediction
    # the output of this function is a single value, the Pearson correlation on the similarity score column of the test data and the predicted similiarity scores for each pair of texts in the test data.
    preproc_test = self.fetch_data(test_data_frame)
    self.classifier.cuda()
    return self.test_model(preproc_test)


