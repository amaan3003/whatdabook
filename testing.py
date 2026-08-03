from db import get_user

import json

user = get_user(8933706980)
data = json.loads(user[1])
print(data.keys())          # dict ke keys dekh
print(data['books'][:2])       # pehli 2 books