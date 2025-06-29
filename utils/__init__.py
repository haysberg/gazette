from sqlmodel import SQLModel, create_engine

engine = create_engine("sqlite:///:memory:", echo=False)
SQLModel.metadata.create_all(engine)