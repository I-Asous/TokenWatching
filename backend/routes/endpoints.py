from fastapi import HTTPException
from main import app
 
import service.db_queries as db
 
## GET

# return a specific users original prompts
@app.get("/users/{user_id}/prompts")
def read_user_prompts(user_id):
    try:
        return db.get_user_input_prompts(user_id)
    except RuntimeError as e:
        # this allows any errors from other files to be seen on the http side!
        raise HTTPException(status_code=500, detail=str(e))
 
# return a specific users optimized prompts
@app.get("/users/{user_id}/optimized-prompts")
def read_user_optimized_prompts(user_id):
    try:
        return db.get_user_optimized_prompts(user_id)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
# return specific users org prompt+optimized prompt
@app.get("/users/{user_id}/prompts-with-optimized")
def read_user_prompts_with_optimized(user_id):
    try:
        return db.get_user_input_and_optimized_prompts(user_id)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
# return a specific users 1 prompt + optimized version of it
@app.get("/users/{user_id}/prompts/{prompt_id}")
def read_user_prompt_with_optimized(user_id, prompt_id):
    try:
        result = db.get_user_prompt_w_optimized(user_id, prompt_id)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return result
 
 
## POST
   
# user submits a prompt
@app.post("/prompt")
def create_prompt(prompt):
    try:
        return db.create_prompt(prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
# optimized prompt from frontend gets send back to backend
# ensure if we need put keeping just in case
@app.post("/optimized-prompts")
def create_optimized_prompt(prompt):
    try:
        return db.create_optimized_prompt(prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
# DELETE
 
# delete a user
@app.delete("/users/{user_id}")
def remove_user(user_id):
    try:
        return db.delete_user(user_id)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
# delete a prompt
@app.delete("/prompts/{prompt_id}")
def remove_prompt(prompt_id):
    try:
        return db.delete_prompt(prompt_id)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
 
 
# UPDATE!!
 
# user updates information
@app.put("/users/{user_id}")
def modify_user(user_id, user):
    try:
        return db.update_user(user, user_id)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))