import string, cgi, time, os
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

import db

class MyRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self, *args, **kwargs):
        try:
            data = db.Db()
            data.setup()

            if self.path == '/api/persons/':
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                data.set_persons()
                resp_data = str(data.get_persons()).replace("'",'"').replace('u\"', '"')
                self.wfile.write(resp_data)
                return

            elif self.path == "/index.html" or self.path == '/':
                # do something else
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()

                self.wfile.write(open('index.html').read())
                return
            else:
                self.send_error(404, "File Not Found %s" % self.path)

        except:
            self.send_error(404, "File Not Found %s" % self.path)

    def do_POST(self):
        self.do_GET() # currently same as post, but can be anything

def main():
    try:
        # you can specify any port you want by changing "8000"
        server = HTTPServer(("", 8000), MyRequestHandler)
        print "starting httpserver"
        server.serve_forever()
    except KeyboardInterrupt:
        print "^C received, shutting down server"
        server.socket.close()

if __name__ == "__main__":
    main()