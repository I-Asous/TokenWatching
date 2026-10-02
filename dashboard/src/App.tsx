import { useEffect } from 'react'
import { AuthenticateWithRedirectCallback, useAuth, useClerk } from '@clerk/react'

// Extension Google sign-in: /?google=1&ext=<id> -> Google -> /sso-callback -> /?google=done -> back to the extension.
const params = new URLSearchParams(window.location.search)
const isCallback = window.location.pathname === '/sso-callback'
export const inGoogleFlow = params.has('google') || isCallback
if (params.get('ext')) sessionStorage.setItem('extId', params.get('ext')!)

function App() {
  const clerk = useClerk()
  const { isLoaded, isSignedIn } = useAuth()

  useEffect(() => {
    if (params.get('google') !== '1' || !isLoaded || isSignedIn || !clerk.client) return
    // Same as Clerk's authenticateWithRedirect, plus prompt=select_account so Google always shows the account chooser.
    void clerk.client.signIn
      .create({ strategy: 'oauth_google', redirectUrl: `${location.origin}/sso-callback`, actionCompleteRedirectUrl: '/?google=done' })
      .then((signIn) => {
        const url = new URL(signIn.firstFactorVerification.externalVerificationRedirectURL!)
        url.searchParams.set('prompt', 'select_account')
        window.location.href = url.toString()
      })
  }, [isLoaded, isSignedIn, clerk])

  useEffect(() => {
    const extId = sessionStorage.getItem('extId')
    const done = params.get('google') === 'done' || (params.get('google') === '1' && isSignedIn)
    if (done && extId) window.location.replace(`chrome-extension://${extId}/index.html?google=done`)
  }, [isSignedIn])

  if (isCallback) {
    return <AuthenticateWithRedirectCallback signInForceRedirectUrl="/?google=done" signUpForceRedirectUrl="/?google=done" />
  }
  if (inGoogleFlow) return null

  return <h1>Token Watching</h1>
}

export default App
