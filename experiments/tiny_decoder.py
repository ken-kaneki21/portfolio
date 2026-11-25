"""A bounded from-scratch CPU decoder for the synthetic extraction experiment."""
from dataclasses import dataclass
import json
import re

import torch
from torch import nn
from torch.nn import functional as F

SPECIAL=['<pad>','<unk>','<eos>']

def pieces(text):
    return re.findall(r'\w+|[^\w\s]',text.lower())

@dataclass
class Codec:
    tokens: list

    def __post_init__(self):
        self.ids={t:i for i,t in enumerate(self.tokens)}

    @classmethod
    def fit(cls,texts):
        return cls(SPECIAL+sorted(set(p for text in texts for p in pieces(text))))

    def encode(self,text):
        return [self.ids.get(p,1) for p in pieces(text)]

    def decode(self,ids):
        return ''.join(self.tokens[i] for i in ids if i!=2)

def template(row,example=None):
    demo='' if example is None else f"Example job: {example['title']} {example['text']} Output: {target(example)}\n"
    return f"{demo}Job: {row['title']} {row['text']} Output:"

def target(row):
    return json.dumps(row['expected'],separators=(',',':'))

class Linear(nn.Linear):
    def add_lora(self,rank):
        self.lora_a=nn.Parameter(torch.empty(rank,self.in_features))
        self.lora_b=nn.Parameter(torch.zeros(self.out_features,rank))
        nn.init.normal_(self.lora_a,std=.025)
        self.lora_scale=8/rank

    def forward(self,x):
        base=super().forward(x)
        if hasattr(self,'lora_a'):
            return base+F.linear(F.linear(x,self.lora_a),self.lora_b)*self.lora_scale
        return base

class Block(nn.Module):
    def __init__(self,width,heads):
        super().__init__()
        self.heads=heads
        self.norm1=nn.LayerNorm(width)
        self.norm2=nn.LayerNorm(width)
        self.qkv=Linear(width,3*width)
        self.out=Linear(width,width)
        self.up=Linear(width,2*width)
        self.down=Linear(2*width,width)

    def forward(self,x):
        b,t,d=x.shape
        q,k,v=self.qkv(self.norm1(x)).reshape(b,t,3,self.heads,d//self.heads).permute(2,0,3,1,4)
        y=F.scaled_dot_product_attention(q,k,v,is_causal=True)
        x=x+self.out(y.transpose(1,2).reshape(b,t,d))
        return x+self.down(F.gelu(self.up(self.norm2(x))))

class Decoder(nn.Module):
    def __init__(self,vocab,width=48,heads=4,layers=2,context=128):
        super().__init__()
        self.context=context
        self.word=nn.Embedding(vocab,width)
        self.pos=nn.Embedding(context,width)
        self.blocks=nn.Sequential(*(Block(width,heads) for _ in range(layers)))
        self.norm=nn.LayerNorm(width)
        self.head=nn.Linear(width,vocab,bias=False)

    def forward(self,x):
        if x.shape[1]>self.context: raise ValueError('context exceeds decoder limit')
        h=self.word(x)+self.pos(torch.arange(x.shape[1],device=x.device))
        return self.head(self.norm(self.blocks(h)))

    def add_lora(self,rank=4):
        self.requires_grad_(False)
        for module in self.modules():
            if isinstance(module,Linear): module.add_lora(rank)

@torch.inference_mode()
def decode(model,codec,prompt,max_new):
    ids=codec.encode(prompt)
    if len(ids)+max_new>model.context: raise ValueError('prompt plus generation exceeds context')
    for _ in range(max_new):
        index=int(model(torch.tensor([ids]))[0,-1].argmax())
        ids.append(index)
        if index==2: return
        yield codec.tokens[index]

def generate(model,codec,prompt,max_new):
    tokens=list(decode(model,codec,prompt,max_new))
    return ''.join(tokens),len(tokens)

def read_model(directory,adapter=False):
    base=torch.load(directory/'base.pt',map_location='cpu',weights_only=True)
    codec=Codec(base['tokens'])
    model=Decoder(len(codec.tokens),**base['architecture'])
    model.load_state_dict(base['weights'])
    if adapter:
        model.add_lora(base['adapter_rank'])
        state=torch.load(directory/'adapter.pt',map_location='cpu',weights_only=True)
        if set(state)!={k for k in model.state_dict() if '.lora_' in k}:
            raise ValueError('adapter keys do not match model')
        missing,extra=model.load_state_dict(state,strict=False)
        if extra or any('.lora_' in k for k in missing):raise ValueError('adapter reload failure')
    return model.eval(),codec
