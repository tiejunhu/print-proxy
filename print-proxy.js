var net = require('net');

var config = {
  port: 9100,
  target: 'localhost:9101'
};

var server = net.createServer(function(socket) {
  socket.on('data', function(chunk) {

  });
});

server.listen(config.port);
console.log('server running on ' + config.port);
