import sys

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import tiktoken
import numpy as np
from scipy.interpolate import interp1d
from typing import List
from sklearn.preprocessing import PolynomialFeatures
import torch
import os

# 环境变量传入
sk_key = os.environ.get('sk-key', 'sk-hv6xtPbK183j3RR306Fe23B6196b4d919a8e854887F6213d')

# 创建一个FastAPI实例
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 创建一个HTTPBearer实例
security = HTTPBearer()

# 预加载模型
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')  # 检测是否有GPU可用，如果有则使用cuda设备，否则使用cpu设备
if torch.cuda.is_available():
    print('本次加载模型的设备为GPU: ', torch.cuda.get_device_name(0))
else:
    print('本次加载模型的设备为CPU.')
model = SentenceTransformer(sys.argv[1], device=device)


class EmbeddingRequest(BaseModel):
    input: List[str]
    model: str


class EmbeddingResponse(BaseModel):
    data: list
    model: str
    object: str
    usage: dict


def num_tokens_from_string(string: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding('cl100k_base')
    num_tokens = len(encoding.encode(string))
    return num_tokens


# 插值法
def interpolate_vector(vector, target_length):
    original_indices = np.arange(len(vector))
    target_indices = np.linspace(0, len(vector) - 1, target_length)
    f = interp1d(original_indices, vector, kind='linear')
    return f(target_indices)


def expand_features(embedding, target_length):
    poly = PolynomialFeatures(degree=2)
    expanded_embedding = poly.fit_transform(embedding.reshape(1, -1))
    expanded_embedding = expanded_embedding.flatten()
    if len(expanded_embedding) > target_length:
        # 如果扩展后的特征超过目标长度，可以通过截断或其他方法来减少维度
        expanded_embedding = expanded_embedding[:target_length]
    elif len(expanded_embedding) < target_length:
        # 如果扩展后的特征少于目标长度，可以通过填充或其他方法来增加维度
        expanded_embedding = np.pad(expanded_embedding, (0, target_length - len(expanded_embedding)))
    return expanded_embedding


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def get_embeddings(request: EmbeddingRequest, credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != sk_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization code",
        )

    # 计算嵌入向量和tokens数量 
    embeddings = [model.encode(text) for text in request.input]

    # 如果嵌入向量的维度不为1536，则使用插值法扩展至1536维度 
    # embeddings = [interpolate_vector(embedding, 1536) if len(embedding) < 1536 else embedding for embedding in embeddings]
    # 如果嵌入向量的维度不为1536，则使用特征扩展法扩展至1536维度 
    embeddings = [expand_features(embedding, 1536) if len(embedding) < 1536 else embedding for embedding in embeddings]

    # Min-Max normalization
    # embeddings = [(embedding - np.min(embedding)) / (np.max(embedding) - np.min(embedding)) if np.max(embedding) != np.min(embedding) else embedding for embedding in embeddings]
    embeddings = [embedding / np.linalg.norm(embedding) for embedding in embeddings]
    # 将numpy数组转换为列表
    embeddings = [embedding.tolist() for embedding in embeddings]
    prompt_tokens = sum(len(text.split()) for text in request.input)
    total_tokens = sum(num_tokens_from_string(text) for text in request.input)

    response = {
        "data": [
            {
                "embedding": embedding,
                "index": index,
                "object": "embedding"
            } for index, embedding in enumerate(embeddings)
        ],
        "model": request.model,
        "object": "list",
        "usage": {
            "prompt_tokens": prompt_tokens,
            "total_tokens": total_tokens,
        }
    }

    return response


if __name__ == "__main__":
    uvicorn.run("embedding_api:app", host='0.0.0.0', port=6006, workers=1)
