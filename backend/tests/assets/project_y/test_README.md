# Project Y
This project uses **Alembic** for managing database migrations.
To apply migrations to the latest version, run:
`alembic upgrade head`

To clear the application cache, use the following internal command:
`php artisan cache:clear`