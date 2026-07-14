export default function middleware(req) {
  const basicAuth = req.headers.get('authorization');

  if (basicAuth) {
    const authValue = basicAuth.split(' ')[1];
    const decoded = atob(authValue);
    
    // THE ACCESS LIST
    // To revoke access, just delete the line. To add a user, add a new line.
    const validCredentials = [
      'admin:admin',      // Username: admin | Password: admin
      'director:pe2026'   // Username: director | Password: pe2026
    ];

    if (validCredentials.includes(decoded)) {
      // Access Granted! Pass the request forward to load the website.
      return; 
    }
  }

  // Access Denied! Force the browser to show the password prompt.
  return new Response('Unauthorized Access', {
    status: 401,
    headers: {
      'WWW-Authenticate': 'Basic realm="Secure Executive Dashboard"'
    }
  });
}
