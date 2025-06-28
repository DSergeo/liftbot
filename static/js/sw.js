self.addEventListener('push', event => {
  const data = event.data.json();
  const options = {
    body: data.body,
    icon: "/static/img/logo.png"
  };
  event.waitUntil(self.registration.showNotification(data.title, options));
});
