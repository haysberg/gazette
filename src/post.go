package main

import (
	"time"

	"gorm.io/gorm"
)

type Post struct {
	gorm.Model
	Link            string `gorm:"primaryKey"`
	Title           string
	Author          *string
	PublicationDate time.Time
}
