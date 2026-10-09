SPRAY_PATHS = """/admin /admin/login /login /manager /manager/html /console
/jmx-console /jenkins /actuator /actuator/env /actuator/heapdump /actuator/jolokia
/actuator/gateway/routes /druid /druid/index.html /swagger /swagger-ui /swagger-ui/
/swagger.json /openapi.json /api-docs /docs /graphql /gql /graphiql /api /api/v1
/mobile/v1 /legacy /phpmyadmin /pma /solr /minio /test /dev /debug /phpinfo.php
/server-status /nginx_status /.git/HEAD /.git/config /.svn/wc.db /.DS_Store /.env
/.env.bak /backup.zip /backup.tar.gz /wwwroot.rar /db.sql /robots.txt /sitemap.xml""".split()
LEAK_PATHS = """/.git/HEAD /.git/config /.git/index /.svn/wc.db /.svn/entries /.DS_Store
/.env /.env.bak /.env.local /backup.zip /backup.tar.gz /wwwroot.rar /db.sql /dump.sql
/dump.rdb /config.php.bak /wp-config.php.bak /web.config.bak /application.properties.bak
/.aws/credentials /.docker/config.json /id_rsa /.bash_history /credentials.json
/service-account.json""".split()
DNS_PREFIXES = """www mail smtp pop imap vpn sso oa oa2 erp crm hr ehr fin pay api
portal admin manage backend gateway git gitlab jenkins sonar nexus test uat sit dev pre
staging prod demo beta shop wx app m h5 es redis mongo mysql minio nacos consul zk kafka
mq rabbit office intranet bbs wiki docs file upload download static img cdn vpn2 ssl
remote rdp ssh ftp webdisk backup old new""".split()
JAVA_PRODUCTS = {
    "/manager": ("Tomcat", "tomcat:s3cret"), "/jmx-console": ("JBoss", "admin:admin"),
    "/console": ("WebLogic", "weblogic:welcome1"), "/actuator": ("Spring Boot", ""),
    "/jenkins": ("Jenkins", ""), "/common/index.jsf": ("GlassFish", "admin:adminadmin"),
    "/jetty": ("Jetty", ""), "/resin-admin": ("Resin", ""), "/t3": ("WebLogic T3", ""),
}
# A provider match alone is insufficient: HTTP status and error evidence are required.
TAKEOVER_FINGERPRINTS = (
    ("Amazon S3", "amazonaws.com", 404, "NoSuchBucket"),
    ("GitHub Pages", "github.io", 404, "There isn't a GitHub Pages site here"),
    ("Heroku", "herokuapp.com", 404, "No such app"),
    ("Azure", "azurewebsites.net", 404, "404 Web Site not found"),
    ("Shopify", "myshopify.com", 404, "Sorry, this shop is currently unavailable"),
    ("Fastly", "fastly.net", 500, "unknown domain"),
    ("Ghost", "ghost.io", 404, "The thing you were looking for is no longer here"),
    ("Bitbucket", "bitbucket.io", 404, "Repository not found"),
    ("Pantheon", "pantheonsite.io", 404, "The gods are wise"),
    ("Surge", "surge.sh", 404, "project not found"),
    ("ReadTheDocs", "readthedocs.io", 404, "unknown domain"),
    ("Tumblr", "tumblr.com", 404, "Whatever you were looking for doesn't currently exist"),
    ("WordPress", "wordpress.com", 404, "Do you want to register"),
    ("Netlify", "netlify.app", 404, "Not Found - Request ID"),
)
