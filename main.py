from datasets import load_dataset
import numpy as np
from transformers import BertTokenizer,BertTokenizerFast
from transformers import BertModel
import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers.optimization import AdamW, get_scheduler
from transformers.trainer_pt_utils import get_parameter_names
from math import ceil
import sys
import time
import datetime
from utils import printProgressBar,chunks


def convert_dataset_to_list(df):
  sentences_list = []
  labels_list = []
  for i in df:
    text = ""
    for word in i['post_tokens']:
      text += " "
      text+= word
    sentences_list.append(text)  
    labels = i['annotators']["label"]
    value = np.argmax(np.bincount(labels))
    labels_list.append(value)
  return sentences_list,labels_list

def validation_score(model,tokenizer,test_loader_full):
  model.eval()
  count = 0
  juste = 0
  out = []
  targets = []
  n = len(test_loader_full)
  #test_loader = [test_loader_full[i] for i in np.random.choice(n, 400)]
  test_loader = test_loader_full
  nb_chunks_val = ceil(len(test_loader)/20)
  chunk = chunks(test_loader,20)
  print("Test val")
  printProgressBar(0, nb_chunks_val, prefix = 'Progress:', suffix = 'Complete', length = 50)
  count = 0
  t0_test = time.time()
  for batch in chunk: ## If you have a DataLoader()  object to get the data. 
    count += 1 
    t1_test = time.time()
    t_done_test = t1_test-t0_test
    printProgressBar(count, nb_chunks_val, prefix = 'Progress:', suffix = 'Complete', length = 50, t_done=t_done_test)  
    data = [sent for sent,id in batch]

    with torch.no_grad():  
      encoding = tokenizer.batch_encode_plus(data, return_tensors='pt', padding=True, truncation=True,max_length=512)
      outputs = model(**encoding)
      outputs = F.softmax(outputs, dim=1)
      
      
    for i in outputs:
      out.append(i.numpy())
    for i in [id for _,id in batch]:
      targets.append(i)


  loss_fct = nn.CrossEntropyLoss()
  loss = loss_fct(torch.FloatTensor(out), torch.LongTensor(targets))
  total = 0
  for i,a in enumerate(out):
    total+=1
    if a.argmax() == targets[i]:
      juste += 1
  print("Accuracy:" + str(juste/total))
  print("Loss:" + str(loss.item()))

"""# Model"""
class CustomBERTModel(nn.Module):
    def __init__(self):
          super(CustomBERTModel, self).__init__()


          self.bert = BertModel.from_pretrained("bert-base-uncased")
          # SET BERT AS UNTRAINABLE
          # for param in self.parameters():
          #     param.requires_grad = False
          ### New layers:
          self.dropout = nn.Dropout(0.1)
          self.linear1 = nn.Linear(768, 3)
          #self.linear2 = nn.Linear(256, 3) ## 3 is the number of classes in this example
          """Initialize the weights"""
          for module in self.children():
            if isinstance(module, nn.Linear):
                module.weight.data.normal_(mean=0.0, std=0.02)
                if module.bias is not None:
                    module.bias.data.zero_()
            elif isinstance(module, nn.Embedding):
                module.weight.data.normal_(mean=0.0, std=0.02)
                if module.padding_idx is not None:
                    module.weight.data[module.padding_idx].zero_()
            elif isinstance(module, nn.LayerNorm):
                module.bias.data.zero_()
                module.weight.data.fill_(1.0)


    def forward(
        self,
        input_ids=None,
        attention_mask=None,
        token_type_ids=None,
        position_ids=None,
        head_mask=None,
        inputs_embeds=None,
        output_attentions=None,
        output_hidden_states=None,
        return_dict=None,
    ):
          outputs = self.bert(
            input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            head_mask=head_mask,
            inputs_embeds=inputs_embeds,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )
          
          # sequence_output has the following shape: (batch_size, sequence_length, 512)
          pooled_output = self.dropout(outputs[1])
          linear1 = self.linear1(pooled_output)
          # linear1 = F.relu(linear1)
          # logits = self.linear2(linear1)
          #linear1_output = self.linear1(sequence_output[:,0,:].view(-1,768)) ## extract the 1st token's embeddings
          #linear2_output = self.linear2(linear1_output)


          return linear1


if __name__ == "__main__":

  dataset_test = load_dataset('hatexplain', split='test')
  valid_texts, valid_labels = convert_dataset_to_list(dataset_test)
  test_loader = [(valid_texts[i],valid_labels[i]) for i in range(len(valid_texts))]
  """# Data loading"""
  dataset_train = load_dataset('hatexplain', split='train')
  train_texts, train_labels = convert_dataset_to_list(dataset_train)
  data_loader = [(train_texts[i],train_labels[i]) for i in range(len(train_texts))]

  """# Tokenization"""

  model_name = "bert-base-uncased"
  tokenizer = BertTokenizerFast.from_pretrained(model_name, do_lower_case=True)


  """# Train"""

  device = torch.device("cpu")

  model = CustomBERTModel() # You can pass the parameters if required to have more flexible model
  #model.to(torch.device(device)) ## can be gpu
  criterion = nn.CrossEntropyLoss() ## If required define your own criterion

  optimizer = torch.optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()),lr=5e-5)
  #optimizer = torch.optim.SGD(model.parameters(), lr=1e-5)


  decay_parameters = get_parameter_names(model, [nn.LayerNorm])
  decay_parameters = [name for name in decay_parameters if "bias" not in name]
  print(len(decay_parameters))
  # self.args.weight_decay

  optimizer_grouped_parameters = [
      {
          "params": [p for n, p in model.named_parameters() if n in decay_parameters],
          "weight_decay": 0.1,
      },
      {
          "params": [p for n, p in model.named_parameters() if n not in decay_parameters],
          "weight_decay": 0.0,
      },
  ]

  optimizer_kwargs = {
      "betas":  (0.9, 0.999),
      "eps": 1e-8,
      "lr": 5e-5,
  }

  # torch.optim.lr_scheduler.LambdaLR()



  # print(optimizer_grouped_parameters[0])

  # print(optimizer)

  #model.to(device)

  nb_chunks = ceil(len(data_loader)/8)

  optimizer = AdamW(optimizer_grouped_parameters, **optimizer_kwargs)

  scheduler = get_scheduler(
                  "linear",
                  optimizer,
                  num_warmup_steps=500,
                  num_training_steps=nb_chunks*3,
              )


  printProgressBar(0, nb_chunks, prefix = 'Progress:', suffix = 'Complete', length = 50)


  # Begin the training
  epochs = [0]
  model.train()
  #model.zero_grad() 
  t0 = time.time()
  for epoch in epochs:
      counter = 0
      
      for batch in chunks(data_loader,8): ## If you have a DataLoader()  object to get the data.
          
          #model.zero_grad() 
          counter += 1
          t1 = time.time()
          t_done = t1-t0
          printProgressBar(counter, nb_chunks, prefix = 'Progress:', suffix = 'Complete', length = 50,t_done = t_done)
          if counter%100==0:
              model.eval()
              print(str( 8*counter) + "/" + str(len(data_loader)))
              print("optimizer")
              print(optimizer)
              validation_score(model,tokenizer,test_loader)
              


          model.train()
          optimizer.zero_grad() 
          
          data = [sent for sent,id in batch]
          targets = torch.tensor([id for sent,id in batch])## assuming that data loader returns a tuple of data and its targets

          encoding = tokenizer.batch_encode_plus(data, return_tensors='pt', padding=True, truncation=True,max_length=512)

          
          outputs = model(**encoding)
          outputs = F.softmax(outputs, dim=1)
          

          loss = criterion(outputs, targets) 
          loss.backward()
          optimizer.step()
          scheduler.step()
