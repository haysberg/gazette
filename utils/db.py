from sqlmodel import SQLModel, create_engine


engine = create_engine("sqlite:///data/data.db", echo=False)
SQLModel.metadata.create_all(engine)
