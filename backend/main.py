from fastapi import FastAPI

app = FastAPI()

# making sure that the api is working :3
@app.get("/")
async def root():
   return {"message": "this is our epic app..."}

### GET METHODS
## this may seem redundant but i decided to implement all of them, but imo i think if we want to see a prompt, we will def want to see the optimized version alongside it as well :/
# return a specific users original prompts

# return a specific users optimized prompts

# return specific users org prompt+optimized prompt

### POST METHODS

# send a prompt to the database :3

# send an optimized prompt to the database :3 (but i also think that this should just be a regular function, but who knows what can happen?)
## trying to think of a way this can be used... :/

### DELETE METHODS
# delete user 
## since enzo is security guy, lets discuss how we should do this bc in a real app they have like secuirty measures to prevent accidental deletion
## but this might be a later issue!

# delete prompt (which also should delete the optimized prompt who is with me!)

# delete optimize (don't even think we need this but it's alwaus good... to have soemthing!)

### UPDATE METHOD
# update user: self explanatory...

# update prompt/optimized prompt: not sure as a now? i thikn if the user modifies the original prompt. but i think that should just not be able to go thru...

