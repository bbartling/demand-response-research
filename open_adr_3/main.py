from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from auth import create_access_token, verify_client

app = FastAPI()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@app.get("/")
async def index():
   return {"message": "Hello World"}

@app.post("/token")
async def token(form_data: OAuth2PasswordRequestForm = Depends()):
    client = verify_client(form_data.username, form_data.password)
    if not client:
        raise HTTPException(status_code=400, detail="Incorrect client credentials")
    access_token = create_access_token(data={"sub": client["client_id"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/payload")
async def protected_endpoint(token: str = Depends(oauth2_scheme)):
    return {"message": 0}
