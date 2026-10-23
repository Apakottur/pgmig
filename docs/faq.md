# FAQ

## Do I need libpq installed?

By default, yes — pgmig requires the Postgres client library (libpq) on the machine. For
standalone / CLI use you can skip that by installing the `binary` extra, which bundles it:

```shell
pip install 'pgmig[binary]'
```
