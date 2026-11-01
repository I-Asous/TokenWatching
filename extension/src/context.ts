import type { Api, ContextCreate, UploadOutcome, UploadUrlResponse } from './contextTypes';

// upload one file to supabase using the signed url they got yay
async function upload(file: File, result: UploadUrlResponse): Promise<ContextCreate> {
  // application/octet-stream is to accept all files when we don't know the file type
  // change in the future when we know which ones to restrict it to
  const mime = file.type || "application/octet-stream"
  const name = file.name
  const size = file.size

  // this should never be null, so if it is something is wrong
  if (result.signed_url != null && result.path != null) {
    const response = await fetch(result.signed_url, { method: "PUT", headers: { "Content-Type": mime }, body: file })
    if(!response.ok) {
      throw new Error(`Status ${response.status}: Failed to upload file: ${response.statusText}`)
    }
    else {
      return { type: "file", file_link: result.path, metadata: { name, size, mime } }
    }
  }
  throw new Error("something went wrong")
}

// user inputs files, we send to supabase to get signed url, and then upload them, with error handling in between
// we can maybe break some of these into helper functions?
export async function uploadContextFiles(api: Api, files: File[]): Promise<UploadOutcome> {
  if (files.length === 0) return { context: [] };

    // we create a list of files that we will upload
    const files_to_upload = files.map((file) => ({
      filename: file.name,
      mime: file.type || "application/octet-stream",
      size: file.size,
    }))
    // we get the signed urls of the files! yay
    const response_signed_url = await api("/contexts/upload-urls", { method: "POST", body: JSON.stringify({ files: files_to_upload}) }) as UploadUrlResponse[]

    // now checking to make sure there are any errors in what the user uploaded...
    const rejected = []

    // if they are rejected, we get the index and error to send to the front end so user knows what needs to be reuploaded
    for(let i = 0; i < response_signed_url.length; i++) {
      // TYPE CHECKING... -_-!!!
      const res = response_signed_url[i] 
      if (res == null) {
        throw new Error("something went wrong")
      }

      if (res["error"] != null) {
        let error: string = res["error"]
        rejected.push({ index: i , error })
      }
    }
      
    // if anything has an error, we send it back. no uploads!
    // this is so we don't have orphaned uplaods and waste space
    if (rejected.length > 0) {
      return { rejected }
    }

    // promise.all runs all the uploads at once bc supabase storage only takes one file at a time!
    const response_upload = await Promise.all(files.map((file,i)=> {
      const result = response_signed_url[i]
      if (!result) throw new Error(`there is no signed url... for ${file.name}`)

      // check to make sure the file corresponds to the right url! bc we don't know if the order can switch up... perhaps it can but actually its unlikely
      if (result.filename != file.name) {
        throw new Error("something went wrong and we were going to upload your file in another place...")
      }
      
      return upload(file,result)
    }))

    return { context: response_upload }

  }

