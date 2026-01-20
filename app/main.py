==> Cloning from https://github.com/jugatre-pixel/lexia360
==> Checking out commit d4698f439b7ceab45722fb86ed95496036695595 in branch main
==> Installing Python version 3.13.4...
==> Using Python version 3.13.4 (default)
==> Docs on specifying a Python version: https://render.com/docs/python-version
==> Using Poetry version 2.1.3 (default)
==> Docs on specifying a Poetry version: https://render.com/docs/poetry-version
==> Running build command 'pip install -r requirements.txt'...
Collecting fastapi==0.95.2 (from -r requirements.txt (line 1))
  Downloading fastapi-0.95.2-py3-none-any.whl.metadata (24 kB)
Collecting uvicorn==0.22.0 (from uvicorn[standard]==0.22.0->-r requirements.txt (line 2))
  Downloading uvicorn-0.22.0-py3-none-any.whl.metadata (6.3 kB)
Collecting sqlmodel==0.0.8 (from -r requirements.txt (line 3))
  Downloading sqlmodel-0.0.8-py3-none-any.whl.metadata (9.7 kB)
Collecting sqlalchemy==2.0.20 (from -r requirements.txt (line 4))
  Downloading SQLAlchemy-2.0.20-py3-none-any.whl.metadata (9.4 kB)
Collecting psycopg2-binary==2.9.6 (from -r requirements.txt (line 5))
  Downloading psycopg2-binary-2.9.6.tar.gz (384 kB)
  Installing build dependencies: started
  Installing build dependencies: finished with status 'done'
  Getting requirements to build wheel: started
  Getting requirements to build wheel: finished with status 'done'
  Preparing metadata (pyproject.toml): started
  Preparing metadata (pyproject.toml): finished with status 'done'
Collecting python-jose==3.3.0 (from python-jose[cryptography]==3.3.0->-r requirements.txt (line 6))
  Downloading python_jose-3.3.0-py2.py3-none-any.whl.metadata (5.4 kB)
Collecting passlib==1.7.4 (from -r requirements.txt (line 7))
  Downloading passlib-1.7.4-py2.py3-none-any.whl.metadata (1.7 kB)
Collecting python-multipart==0.0.6 (from -r requirements.txt (line 8))
  Downloading python_multipart-0.0.6-py3-none-any.whl.metadata (2.5 kB)
Collecting email-validator==1.3.1 (from -r requirements.txt (line 9))
  Downloading email_validator-1.3.1-py2.py3-none-any.whl.metadata (23 kB)
Collecting reportlab==4.0.0 (from -r requirements.txt (line 10))
  Downloading reportlab-4.0.0-py3-none-any.whl.metadata (1.3 kB)
Collecting pytest==7.4.0 (from -r requirements.txt (line 11))
  Downloading pytest-7.4.0-py3-none-any.whl.metadata (8.0 kB)
Collecting pydantic!=1.7,!=1.7.1,!=1.7.2,!=1.7.3,!=1.8,!=1.8.1,<2.0.0,>=1.6.2 (from fastapi==0.95.2->-r requirements.txt (line 1))
  Downloading pydantic-1.10.26-cp313-cp313-manylinux2014_x86_64.manylinux_2_17_x86_64.whl.metadata (155 kB)
Collecting starlette<0.28.0,>=0.27.0 (from fastapi==0.95.2->-r requirements.txt (line 1))
  Downloading starlette-0.27.0-py3-none-any.whl.metadata (5.8 kB)
Collecting click>=7.0 (from uvicorn==0.22.0->uvicorn[standard]==0.22.0->-r requirements.txt (line 2))
  Downloading click-8.3.1-py3-none-any.whl.metadata (2.6 kB)
Collecting h11>=0.8 (from uvicorn==0.22.0->uvicorn[standard]==0.22.0->-r requirements.txt (line 2))
  Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
INFO: pip is looking at multiple versions of sqlmodel to determine which version is compatible with other requirements. This could take a while.
ERROR: Cannot install -r requirements.txt (line 3) and sqlalchemy==2.0.20 because these package versions have conflicting dependencies.
The conflict is caused by:
    The user requested sqlalchemy==2.0.20
    sqlmodel 0.0.8 depends on SQLAlchemy<=1.4.41 and >=1.4.17
To fix this you could try to:
1. loosen the range of package versions you've specified
2. remove package versions to allow pip to attempt to solve the dependency conflict
[notice] A new release of pip is available: 25.1.1 -> 25.3
[notice] To update, run: pip install --upgrade pip
ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts
==> Build failed 😞
==> Common ways to troubleshoot your deploy: https://render.com/docs/troubleshooting-deploys
